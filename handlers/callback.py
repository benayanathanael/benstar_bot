from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from config import HARI, nama_user, partner_id, USER_A_ID, USER_B_ID
from database import db
from helpers import esc, rupiah
from keyboards import (
    pilih_hari_kb, edit_field_kb_jadwal, edit_field_kb_pen, aksi_jadwal_kb, aksi_pen_kb
)
from states import set_state, clear_state
from handlers import add, jadwal

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data

    # ---- Tambah ----
    if data == "add:jadwal":
        await add.start_add_jadwal(update, context)
    elif data == "add:pen":
        await add.start_add_pen(update, context)

    # ---- Pilih hari (jadwal form) ----
    elif data.startswith("jf:hari:"):
        await q.answer()
        hari = int(data.split(":")[2])
        _, ctx = _load_state(uid)
        ctx = ctx or {}
        ctx["hari"] = hari
        ctx["step"] = "jam_mulai"
        set_state(uid, "jf", ctx)
        await q.edit_message_text(
            f"Hari: <b>{HARI[hari]}</b>\n\nJam mulai? (contoh: <code>08:00</code>)",
            parse_mode="HTML"
        )

    # ---- Pilih pembayar (pen form) ----
    elif data.startswith("pf:bayar:"):
        await q.answer()
        bayar_id = int(data.split(":")[2])
        state, ctx = _load_state(uid)
        if state != "pf" or not ctx or ctx.get("step") != "bayar":
            await q.edit_message_text("Sesi kadaluarsa. Ulangi dari menu.")
            return
        tanggal = __import__("helpers").tanggal_hari_ini()
        with db() as conn:
            conn.execute("""
                INSERT INTO pengeluaran (nominal, keterangan, dibayar_oleh, tanggal)
                VALUES (?, ?, ?, ?)
            """, (ctx["nominal"], ctx["keterangan"], bayar_id, tanggal))
            my_pref = conn.execute(
                "SELECT notif_transaksi FROM preferences WHERE user_id=?",
                (uid,)
            ).fetchone()
        clear_state(uid)
        await q.edit_message_text(
            f"✅ Tersimpan: <b>{rupiah(ctx['nominal'])}</b>\n"
            f"{esc(ctx['keterangan'])} — oleh {nama_user(bayar_id)}",
            parse_mode="HTML"
        )

        # Notif ke pasangan kalau user ini menyalakan notif_transaksi
        if my_pref and my_pref["notif_transaksi"]:
            pid = partner_id(uid)
            if pid:
                try:
                    await context.bot.send_message(
                        pid,
                        f"💰 <b>{nama_user(uid)}</b> mencatat pengeluaran\n"
                        f"{esc(ctx['keterangan'])} — {rupiah(ctx['nominal'])}",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

    # ---- Navigasi jadwal ----
    elif data.startswith("nav:"):
        await q.answer()
        offset = int(data.split(":")[1])
        await jadwal._render_jadwal(update, context, offset, edit_mode=True)

    # ---- Detail jadwal ----
    elif data.startswith("detail_jadwal:"):
        await q.answer()
        jid = int(data.split(":")[1])
        await jadwal.show_detail_jadwal(update, context, jid)

    # ---- Navigasi keuangan ----
    elif data.startswith("nav_pen:"):
        await q.answer()
        offset = int(data.split(":")[1])
        from handlers import keuangan
        await keuangan.show_keuangan(update, context, offset=offset, edit_mode=True)

    # ---- Edit jadwal: pilih field ----
    elif data.startswith("edit_jadwal:"):
        await q.answer()
        jid = int(data.split(":")[1])
        await q.edit_message_text(
            "Pilih field yang mau diedit:",
            reply_markup=edit_field_kb_jadwal(jid)
        )

    # ---- Edit jadwal: pilih field spesifik ----
    elif data.startswith("ej:"):
        await q.answer()
        _, jid_str, field = data.split(":")
        jid = int(jid_str)
        if field == "hari":
            set_state(uid, "ej_hari_wait", {"jadwal_id": jid})
            await q.edit_message_text(
                "Pilih hari baru:",
                reply_markup=pilih_hari_kb(prefix=f"ej_hari:{jid}")
            )
        else:
            label = {"jam_mulai": "jam mulai", "jam_selesai": "jam selesai",
                     "mk": "mata kuliah", "ruangan": "ruangan"}[field]
            set_state(uid, "ej_wait", {"jadwal_id": jid, "field": field})
            await q.edit_message_text(
                f"Ketik {label} baru:\n\n<i>(/cancel untuk batal)</i>",
                parse_mode="HTML"
            )

    # ---- Pilih hari saat edit ----
    elif data.startswith("ej_hari:"):
        await q.answer()
        _, jid_str, hari_str = data.split(":")
        jid, hari = int(jid_str), int(hari_str)
        with db() as conn:
            conn.execute("UPDATE jadwal SET hari=? WHERE id=?", (hari, jid))
            row = conn.execute("SELECT * FROM jadwal WHERE id=?", (jid,)).fetchone()
        clear_state(uid)
        text = (
            f"✅ Jadwal diperbarui\n\n"
            f"<b>{esc(row['mata_kuliah'])}</b>\n"
            f"{HARI[row['hari']]} {row['jam_mulai']}–{row['jam_selesai']}"
            + (f"\n📍 {esc(row['ruangan'])}" if row["ruangan"] else "")
        )
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=aksi_jadwal_kb(jid))

    # ---- Hapus jadwal (Konfirmasi) ----
    elif data.startswith("del_jadwal:"):
        await q.answer()
        jid = int(data.split(":")[1])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ya, Hapus", callback_data=f"confirm_del_jadwal:{jid}"),
             InlineKeyboardButton("❌ Batal", callback_data=f"detail_jadwal:{jid}")]
        ])
        await q.edit_message_text("Yakin mau hapus jadwal ini?", reply_markup=kb)

    elif data.startswith("confirm_del_jadwal:"):
        await q.answer("Dihapus")
        jid = int(data.split(":")[1])
        with db() as conn:
            conn.execute("UPDATE jadwal SET aktif=0 WHERE id=?", (jid,))
        await q.edit_message_text("🗑 Jadwal dihapus.")

    # ---- Edit pengeluaran: pilih field ----
    elif data.startswith("edit_pen:"):
        await q.answer()
        pid = int(data.split(":")[1])
        await q.edit_message_text(
            "Pilih field yang mau diedit:",
            reply_markup=edit_field_kb_pen(pid)
        )

    # ---- Edit pengeluaran: pilih field ----
    elif data.startswith("ep:"):
        await q.answer()
        _, pid_str, field = data.split(":")
        pid = int(pid_str)
        if field == "bayar":
            set_state(uid, "ep_bayar_wait", {"pen_id": pid})
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"👤 {nama_user(USER_A_ID)}", callback_data=f"ep_bayar:{pid}:{USER_A_ID}")],
                [InlineKeyboardButton(f"👤 {nama_user(USER_B_ID)}", callback_data=f"ep_bayar:{pid}:{USER_B_ID}")],
                [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
            ])
            await q.edit_message_text("Pilih pembayar baru:", reply_markup=kb)
        else:
            label = {"nominal": "nominal", "keterangan": "keterangan"}[field]
            set_state(uid, "ep_wait", {"pen_id": pid, "field": field})
            await q.edit_message_text(
                f"Ketik {label} baru:\n\n<i>(/cancel untuk batal)</i>",
                parse_mode="HTML"
            )

    # ---- Pilih bayar saat edit ----
    elif data.startswith("ep_bayar:"):
        await q.answer()
        _, pid_str, bayar_str = data.split(":")
        pid, bayar = int(pid_str), int(bayar_str)
        with db() as conn:
            conn.execute("UPDATE pengeluaran SET dibayar_oleh=? WHERE id=?", (bayar, pid))
            row = conn.execute("SELECT * FROM pengeluaran WHERE id=?", (pid,)).fetchone()
        clear_state(uid)
        text = (
            f"✅ Pengeluaran diperbarui\n\n"
            f"<b>{esc(row['keterangan'])}</b>\n"
            f"{rupiah(row['nominal'])} • oleh {nama_user(row['dibayar_oleh'])} • {row['tanggal']}"
        )
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=aksi_pen_kb(pid))

    # ---- Hapus pengeluaran ----
    elif data.startswith("del_pen:"):
        await q.answer("Dihapus")
        pid = int(data.split(":")[1])
        with db() as conn:
            conn.execute("UPDATE pengeluaran SET dihapus=1 WHERE id=?", (pid,))
        await q.edit_message_text("🗑 Pengeluaran dihapus.")

    # ---- Settings: toggle ----
    elif data.startswith("set:tg:"):
        await q.answer()
        which = data.split(":")[2]
        col = {
            "self": "notif_kelas_self",
            "partner": "notif_kelas_partner",
            "trx": "notif_transaksi",
        }.get(which)
        if not col:
            return
        with db() as conn:
            conn.execute(
                f"UPDATE preferences SET {col} = 1 - {col} WHERE user_id=?",
                (uid,)
            )
        await _refresh_settings(q, uid)

    # ---- Settings: cycle menit ----
    elif data == "set:menit":
        await q.answer()
        from services.scheduler import MENIT_CYCLE
        with db() as conn:
            pref = conn.execute(
                "SELECT menit_sebelum FROM preferences WHERE user_id=?", (uid,)
            ).fetchone()
        current = pref["menit_sebelum"]
        try:
            idx = MENIT_CYCLE.index(current)
            nxt = MENIT_CYCLE[(idx + 1) % len(MENIT_CYCLE)]
        except ValueError:
            nxt = 15
        with db() as conn:
            conn.execute(
                "UPDATE preferences SET menit_sebelum=? WHERE user_id=?",
                (nxt, uid)
            )
        await _refresh_settings(q, uid)

    elif data == "cancel":
        await q.answer()
        clear_state(uid)
        await q.edit_message_text("Dibatalkan.")

def _load_state(uid):
    from states import get_state
    return get_state(uid)

async def _refresh_settings(q, uid):
    from keyboards import settings_kb
    from handlers.settings import _settings_text
    with db() as conn:
        pref = conn.execute(
            "SELECT * FROM preferences WHERE user_id=?", (uid,)
        ).fetchone()
    await q.edit_message_text(
        _settings_text(uid, pref),
        parse_mode="HTML",
        reply_markup=settings_kb(pref)
    )