import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import TZ, now_wib, nama_user, partner_id
from database import db, log_once

logger = logging.getLogger(__name__)

_scheduler = None
_last_cleanup = datetime.min.replace(tzinfo=TZ)

MENIT_CYCLE = [5, 10, 15, 20, 30, 45, 60]


async def _scan(bot):
    global _last_cleanup
    try:
        now = now_wib()
        today = now.strftime("%Y-%m-%d")
        hari = now.weekday()
        jam_sekarang = now.hour * 60 + now.minute

        with db() as conn:
            rows = conn.execute(
                "SELECT * FROM jadwal WHERE hari=? AND aktif=1", (hari,)
            ).fetchall()
            prefs = {
                p["user_id"]: dict(p)
                for p in conn.execute("SELECT * FROM preferences").fetchall()
            }

        for row in rows:
            await _check_jadwal(bot, row, today, jam_sekarang, prefs)

        # Cleanup notif_log > 7 hari sekali per jam
        if (now - _last_cleanup).total_seconds() > 3600:
            with db() as conn:
                conn.execute("DELETE FROM notif_log WHERE sent_at < datetime('now', '-7 days')")
            _last_cleanup = now
    except Exception as e:
        logger.exception(f"Scan error: {e}")


async def _check_jadwal(bot, row, today, jam_sekarang, prefs):
    jadwal_id = row["id"]
    user_id = row["user_id"]
    pref = prefs.get(user_id)
    if not pref:
        return

    try:
        h, m = map(int, row["jam_mulai"].split(":"))
    except (ValueError, AttributeError):
        return
    menit_mulai = h * 60 + m

    # 1. Reminder ke diri sendiri: kirim setelah reminder time lewat, sebelum kelas mulai
    if pref["notif_kelas_self"]:
        menit_sebelum = pref["menit_sebelum"]
        selisih = jam_sekarang - (menit_mulai - menit_sebelum)
        if selisih >= 0 and jam_sekarang < menit_mulai:
            kunci = f"self:{jadwal_id}:{today}"
            if log_once(kunci):
                sisa = menit_mulai - jam_sekarang
                ruang = f" • {row['ruangan']}" if row["ruangan"] else ""
                try:
                    await bot.send_message(
                        user_id,
                        f"⏰ <b>{sisa} menit lagi</b>\n"
                        f"{row['mata_kuliah']}\n"
                        f"{row['jam_mulai']}–{row['jam_selesai']}{ruang}",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(f"Reminder self gagal (user {user_id}): {e}")

    # 2. Notif ke pasangan tepat saat kelas mulai (window 5 menit untuk catch-up)
    if pref["notif_kelas_partner"]:
        selisih = jam_sekarang - menit_mulai
        if 0 <= selisih <= 5:
            kunci = f"partner:{jadwal_id}:{today}"
            if log_once(kunci):
                pid = partner_id(user_id)
                if pid:
                    ruang = f" • {row['ruangan']}" if row["ruangan"] else ""
                    try:
                        await bot.send_message(
                            pid,
                            f"🟦 <b>{nama_user(user_id)}</b> sedang kelas\n"
                            f"{row['mata_kuliah']}\n"
                            f"{row['jam_mulai']}–{row['jam_selesai']}{ruang}",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.warning(f"Notif partner gagal (user {pid}): {e}")


def start_scheduler(bot):
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")
    _scheduler.add_job(
        _scan,
        IntervalTrigger(seconds=45),
        args=[bot],
        id="benstar_scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info("⏰ Scheduler started (interval 45s)")
