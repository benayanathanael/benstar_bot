import re

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from config import HARI, nama_user, USER_A_ID, USER_B_ID, USER_A_NAMA, USER_B_NAMA
from database import db
from helpers import valid_jam, valid_nominal, rupiah, esc, tanggal_hari_ini
from keyboards import (
    pilih_hari_kb, pilih_pemilik_jadwal_kb, pilih_bayar_kb, menu_utama,
    aksi_jadwal_kb, aksi_pen_kb,
)
from states import set_state, clear_state

# Buat keyboard batal sekali saja
KB_BATAL = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data="cancel")]])

def parse_jadwal_text(text):
    # 1. Ekstrak Jam (contoh: 07.00 - 09.30)
    time_match = re.search(
        r'(\d{1,2}[:.]\d{2})\s*(?:-|s/d|sampai)\s*(\d{1,2}[:.]\d{2})',
        text,
        re.IGNORECASE,
    )
    if not time_match:
        return None

    jm = time_match.group(1).replace('.', ':')
    js = time_match.group(2).replace('.', ':')
    if len(jm.split(':')[0]) == 1:
        jm = '0' + jm
    if len(js.split(':')[0]) == 1:
        js = '0' + js

    # 2. Ekstrak Matkul
    mk_match = re.search(
        r'(?:matkul|mata kuliah)\s+([^\n]+?)(?=\s+(?:hari|dosen|jam|ruang)|$)',
        text,
        re.IGNORECASE,
    )
    if mk_match:
        mk = mk_match.group(1).strip()
    else:
        parts = re.split(r'dosen|jam|ruang', text, flags=re.IGNORECASE)
        mk = parts[0].replace("aku mau nambah jadwal", "").replace("matkul", "").strip()

    # 3. Ekstrak Ruangan & Dosen
    r_match = re.search(r'ruang(?:an)?\s*[:=]?\s*([^\n]+)', text, re.IGNORECASE)
    ruang = r_match.group(1).strip() if r_match else ""

    d_match = re.search(r'dosen\s*[:=]?\s*([^\n]+)', text, re.IGNORECASE)
    dosen = d_match.group(1).strip() if d_match else ""

    if dosen and ruang:
        ruang = f"{ruang} ({dosen})"
    elif dosen:
        ruang = dosen

    # 4. Ekstrak Hari
    hari_map = {
        "senin": 0,
        "selasa": 1,
        "rabu": 2,
        "kamis": 3,
        "jumat": 4,
        "sabtu": 5,
        "minggu": 6,
    }
    hari = -1
    for h_name, h_idx in hari_map.items():
        if h_name in text.lower():
            hari = h_idx
            break

    return {
        "matkul": mk,
        "jam_mulai": jm,
        "jam_selesai": js,
        "ruangan": ruang,
        "hari": hari,
    }

def parse_pen_text(text):
    amount_match = re.search(
        r'(?<!\w)(\d{1,3}(?:[.,]\d{3})+|\d+)(?:\s*(rb|ribu|k))?(?!\w)',
        text,
        re.IGNORECASE,
    )
    if not amount_match:
        return None

    amount_text = amount_match.group(1).replace(".", "").replace(",", "")
    nominal = int(amount_text)
    unit = (amount_match.group(2) or "").lower()
    if unit in ("rb", "ribu", "k"):
        nominal *= 1000
    if nominal <= 0 or nominal > 1_000_000_000:
        return None

    keterangan = (
        text[:amount_match.start()] + " " + text[amount_match.end():]
    )
    keterangan = re.sub(
        r'\b(?:aku|mau|nambah|tambah|tambahin|bikin|buat|catat|catet|input|'
        r'pengeluaran|uang|duit|bayar|beli|habis)\b',
        " ",
        keterangan,
        flags=re.IGNORECASE,
    )
    keterangan = re.sub(r'\s+', ' ', keterangan).strip(" :-")
    if not keterangan:
        keterangan = "Pengeluaran"

    return {
        "nominal": nominal,
        "keterangan": keterangan,
        "tanggal": tanggal_hari_ini(),
    }

def parse_jadwal_list_text(text):
    hari_map = {
        "senin": 0,
        "selasa": 1,
        "rabu": 2,
        "kamis": 3,
        "jumat": 4,
        "sabtu": 5,
        "minggu": 6,
    }
    current_day = None
    current_schedule = None
    pending_course = None
    pending_dosen = ""
    schedules = []

    for raw_line in text.splitlines():
        line = raw_line.strip().strip("-•").strip()
        if not line:
            continue

        day_match = re.fullmatch(
            r'(?:.*?[-:]\s*)?(?:hari\s+)?'
            r'(senin|selasa|rabu|kamis|jumat|sabtu|minggu)',
            line,
            re.IGNORECASE,
        )
        if day_match:
            current_day = hari_map[day_match.group(1).lower()]
            current_schedule = None
            pending_course = None
            pending_dosen = ""
            continue
        if (
            current_day is None
            and not re.search(r'\d{1,2}[:.]\d{2}', line)
            and re.search(r'\b(?:senin|selasa|rabu|kamis|jumat|sabtu|minggu)\b', line, re.IGNORECASE)
        ):
            day_name = re.search(
                r'\b(senin|selasa|rabu|kamis|jumat|sabtu|minggu)\b',
                line,
                re.IGNORECASE,
            ).group(1).lower()
            current_day = hari_map[day_name]
            continue

        time_match = re.fullmatch(
            r'(\d{1,2}[:.]\d{2})\s*(?:-|–|—|s/d|sampai)\s*'
            r'(\d{1,2}[:.]\d{2})(?:\s*\|\s*(.*))?',
            line,
            re.IGNORECASE,
        )
        if time_match and current_day is not None:
            if pending_course is not None:
                current_schedule = {
                    "hari": current_day,
                    "jam_mulai": time_match.group(1).replace(".", ":"),
                    "jam_selesai": time_match.group(2).replace(".", ":"),
                    "matkul": pending_course,
                    "dosen": pending_dosen,
                }
            else:
                current_schedule = {
                    "hari": current_day,
                    "jam_mulai": time_match.group(1).replace(".", ":"),
                    "jam_selesai": time_match.group(2).replace(".", ":"),
                }
            for key in ("jam_mulai", "jam_selesai"):
                hour, minute = current_schedule[key].split(":")
                current_schedule[key] = f"{int(hour):02d}:{minute}"
            current_schedule["ruangan"] = (time_match.group(3) or "").strip()
            schedules.append(current_schedule)
            pending_course = None
            pending_dosen = ""
            continue

        if pending_course is not None and re.match(r'^dosen\s*:', line, re.IGNORECASE):
            pending_dosen = re.sub(r'^dosen\s*:\s*', '', line, flags=re.IGNORECASE).strip()
            continue

        if current_schedule is not None:
            if "matkul" in current_schedule:
                if not current_schedule["ruangan"] and "|" not in line:
                    current_schedule["ruangan"] = line.strip()
                    current_schedule = None
                    continue
                pending_course = line.lstrip("-• ").strip()
                pending_dosen = ""
                current_schedule = None
                continue
            parts = re.split(r'\s+[—–-]\s+', line, maxsplit=1)
            matkul = re.split(r'\s+di\s+jadwal\b', parts[0], maxsplit=1, flags=re.IGNORECASE)[0]
            current_schedule["matkul"] = matkul.strip()
            current_schedule["dosen"] = parts[1].strip() if len(parts) == 2 else ""
            current_schedule["ruangan"] = ""
            current_schedule = None
        elif current_day is not None:
            pending_course = line.lstrip("-• ").strip()

    valid = [
        item for item in schedules
        if item.get("matkul")
    ]
    return valid or None

async def start_add_jadwal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    set_state(uid, "jf", {"step": "hari"})
    await q.answer()
    await q.edit_message_text(
        "Jadwal ini untuk siapa?",
    )

async def start_add_pen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    set_state(uid, "pf", {"step": "nominal"})
    await q.answer()
    await q.edit_message_text(
        "Ketik nominal pengeluaran:\n(contoh: <code>25000</code> atau <code>25.000</code>)",
        parse_mode="HTML"
    )

def _valid_form_jam(text: str) -> str | None:
    text = text.strip().rstrip(" .,!?:;")
    normalized = valid_jam(text)
    if normalized:
        return normalized

    match = re.fullmatch(r"(?:jam|pukul)\s+(.+)", text.lower())
    if not match:
        return None

    spoken = match.group(1)
    period = None
    for suffix in ("pagi", "siang", "sore", "malam"):
        if spoken.endswith(f" {suffix}"):
            spoken = spoken[: -(len(suffix) + 1)]
            period = suffix
            break

    hours = {
        "satu": 1,
        "dua": 2,
        "tiga": 3,
        "empat": 4,
        "lima": 5,
        "enam": 6,
        "tujuh": 7,
        "delapan": 8,
        "sembilan": 9,
        "sepuluh": 10,
        "sebelas": 11,
        "dua belas": 12,
    }
    hour = hours.get(spoken)
    if hour is None and spoken.isdecimal():
        hour = int(spoken)
    if hour is None or not 0 <= hour <= 23:
        return None
    if period == "pagi" and hour == 12:
        hour = 0
    elif period in ("siang", "sore", "malam") and hour < 12:
        hour += 12
    return f"{hour:02d}:00"


async def _handle_jadwal_form(update, uid, ctx, text):
    step = ctx["step"]

    if step == "jam_mulai":
        jam = _valid_form_jam(text)
        if not jam:
            await update.message.reply_text(
                "❌ Format jam salah.\nKetik seperti <code>08:00</code> atau <code>08.00</code>",
                parse_mode="HTML"
            )
            return
        ctx["jam_mulai"] = jam
        ctx["step"] = "jam_selesai"
        set_state(uid, "jf", ctx)
        await update.message.reply_text(
            "Jam selesai? (contoh: <code>09:40</code>)", 
            parse_mode="HTML"
        )

    elif step == "jam_selesai":
        jam = _valid_form_jam(text)
        if not jam:
            await update.message.reply_text(
                "❌ Format jam salah.\nKetik seperti <code>09:40</code>", 
                parse_mode="HTML", reply_markup=KB_BATAL
            )
            return
        ctx["jam_selesai"] = jam
        ctx["step"] = "mk"
        set_state(uid, "jf", ctx)
        await update.message.reply_text("Mata kuliah apa?")

    elif step == "mk":
        if not text:
            return
        ctx["mata_kuliah"] = text
        ctx["step"] = "dosen"
        set_state(uid, "jf", ctx)
        await update.message.reply_text(
            "Nama dosen? (ketik <code>/skip</code> kalau tidak ada)",
            parse_mode="HTML"
        )

    elif step == "dosen":
        ctx["dosen"] = None if text.lower() in ("/skip", "skip", "-") else text
        ctx["step"] = "ruangan"
        set_state(uid, "jf", ctx)
        await update.message.reply_text(
            "Ruangan? (ketik <code>/skip</code> kalau tidak ada)",
            parse_mode="HTML"
        )

    elif step == "ruangan":
        ruangan = None if text.lower() in ("/skip", "skip", "-") else text
        hari = ctx["hari"]
        with db() as conn:
            conn.execute("""
                INSERT INTO jadwal
                    (user_id, hari, jam_mulai, jam_selesai, mata_kuliah, dosen, ruangan)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ctx.get("owner_id", uid), hari, ctx["jam_mulai"], ctx["jam_selesai"],
                ctx["mata_kuliah"], ctx.get("dosen"), ruangan,
            ))
        clear_state(uid)
        await update.message.reply_text(
            f"✅ Jadwal <b>{esc(ctx['mata_kuliah'])}</b> tersimpan!\n"
            f"{HARI[hari]} {ctx['jam_mulai']}–{ctx['jam_selesai']}"
            + (f" di {esc(ruangan)}" if ruangan else ""),
            parse_mode="HTML",
        )

async def _handle_pen_form(update, uid, ctx, text):
    step = ctx["step"]

    if step == "nominal":
        n = valid_nominal(text)
        if not n:
            await update.message.reply_text(
                "❌ Nominal tidak valid.\nKetik angka saja, contoh: <code>45000</code>", 
                parse_mode="HTML"
            )
            return
        ctx["nominal"] = n
        ctx["step"] = "keterangan"
        set_state(uid, "pf", ctx)
        await update.message.reply_text(
            "Keterangan pengeluaran? (contoh: <i>makan siang</i>)", 
            parse_mode="HTML"
        )

    elif step == "keterangan":
        if not text:
            return
        ctx["keterangan"] = text
        ctx["step"] = "bayar"
        set_state(uid, "pf", ctx)
        await update.message.reply_text(
            f"Nominal: <b>{rupiah(ctx['nominal'])}</b>\nKeterangan: {esc(text)}\n\nSiapa yang bayar?",
            parse_mode="HTML",
        )

async def handle_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state: str,
    ctx: dict,
    text_override: str | None = None,
):
    uid = update.effective_user.id
    text = (
        text_override if text_override is not None else update.message.text
    ).strip()

    if ctx is None:
        ctx = {}

    if state == "jf_nl_owner":
        owner_id = _owner_id_from_text(text, uid)
        if owner_id is None:
            await update.message.reply_text("Ketik pemilik jadwal: Benaya atau Agnes.")
            return
        with db() as conn:
            conn.execute("""
                INSERT INTO jadwal
                    (user_id, hari, jam_mulai, jam_selesai, mata_kuliah, ruangan)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                owner_id, ctx["hari"], ctx["jam_mulai"], ctx["jam_selesai"],
                ctx["matkul"], ctx["ruangan"],
            ))
        clear_state(uid)
        await update.message.reply_text(
            f"Jadwal {ctx['matkul']} tersimpan untuk {nama_user(owner_id)}."
        )
    elif state == "jf_nl_hari":
        hari = _day_from_text(text)
        if hari is None:
            await update.message.reply_text("Ketik nama hari: Senin sampai Minggu.")
            return
        ctx["hari"] = hari
        set_state(uid, "jf_nl_owner", ctx)
        await update.message.reply_text("Ketik pemilik jadwal: Benaya atau Agnes.")
    elif state == "bulk_jadwal_action":
        if text.lower() in ("batal", "/cancel"):
            clear_state(uid)
            await update.message.reply_text("Dibatalkan.")
        elif "simpan" in text.lower():
            ctx["action"] = "save"
            set_state(uid, "bulk_jadwal_owner", ctx)
            await update.message.reply_text("Ketik pemilik jadwal: Benaya atau Agnes.")
        else:
            await update.message.reply_text("Ketik 'simpan semua' atau 'batal'.")
    elif state == "bulk_jadwal_owner":
        owner_id = _owner_id_from_text(text, uid)
        if owner_id is None:
            await update.message.reply_text("Ketik pemilik jadwal: Benaya atau Agnes.")
            return
        with db() as conn:
            for item in ctx["items"]:
                conn.execute("""
                    INSERT INTO jadwal
                        (user_id, hari, jam_mulai, jam_selesai, mata_kuliah, dosen, ruangan)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    owner_id, item["hari"], item["jam_mulai"], item["jam_selesai"],
                    item["matkul"], item["dosen"] or None, item["ruangan"] or None,
                ))
        clear_state(uid)
        await update.message.reply_text(
            f"{len(ctx['items'])} jadwal tersimpan untuk {nama_user(owner_id)}."
        )
    elif state == "jf":
        await _handle_jadwal_form(update, uid, ctx, text)
    elif state == "pf":
        await _handle_pen_form(update, uid, ctx, text)
    elif state == "ej_wait":
        jid = ctx.get("jadwal_id")
        field = ctx.get("field")
        col_map = {
            "jam_mulai": "jam_mulai",
            "jam_selesai": "jam_selesai",
            "mk": "mata_kuliah",
            "dosen": "dosen",
            "ruangan": "ruangan"
        }
        col = col_map.get(str(field))
        if not col or not jid:
            clear_state(uid)
            await update.message.reply_text("Terjadi kesalahan. Silakan ulangi.", reply_markup=menu_utama())
            return

        val = text
        if field in ("jam_mulai", "jam_selesai"):
            val = valid_jam(text)
            if not val:
                await update.message.reply_text(
                    "❌ Format jam salah. Contoh: <code>08:00</code>",
                    parse_mode="HTML",
                    reply_markup=KB_BATAL
                )
                return
        elif field == "dosen":
            val = None if text.lower() in ("/skip", "skip", "-") else text
        elif field == "ruangan":
            val = None if text.lower() in ("/skip", "skip", "-") else text

        with db() as conn:
            conn.execute(f"UPDATE jadwal SET {col}=? WHERE id=?", (val, jid))
            row = conn.execute("SELECT * FROM jadwal WHERE id=?", (jid,)).fetchone()

        clear_state(uid)
        if row:
            ruang_str = f"\n📍 {esc(row['ruangan'])}" if row["ruangan"] else ""
            await update.message.reply_text(
                f"✅ Jadwal diperbarui\n\n"
                f"<b>{esc(row['mata_kuliah'])}</b>\n"
                f"{HARI[row['hari']]} {row['jam_mulai']}–{row['jam_selesai']}{ruang_str}",
                parse_mode="HTML",
                reply_markup=aksi_jadwal_kb(jid)
            )
        else:
            await update.message.reply_text("✅ Jadwal diperbarui.", reply_markup=menu_utama())

    elif state == "ep_wait":
        pid = ctx.get("pen_id")
        field = ctx.get("field")
        col_map = {
            "nominal": "nominal",
            "keterangan": "keterangan"
        }
        col = col_map.get(str(field))
        if not col or not pid:
            clear_state(uid)
            await update.message.reply_text("Terjadi kesalahan. Silakan ulangi.", reply_markup=menu_utama())
            return

        val = text
        if field == "nominal":
            val = valid_nominal(text)
            if not val:
                await update.message.reply_text(
                    "❌ Nominal tidak valid. Contoh: <code>25000</code>",
                    parse_mode="HTML",
                    reply_markup=KB_BATAL
                )
                return

        with db() as conn:
            conn.execute(f"UPDATE pengeluaran SET {col}=? WHERE id=?", (val, pid))
            row = conn.execute("SELECT * FROM pengeluaran WHERE id=?", (pid,)).fetchone()

        clear_state(uid)
        if row:
            await update.message.reply_text(
                f"✅ Pengeluaran diperbarui\n\n"
                f"<b>{esc(row['keterangan'])}</b>\n"
                f"{rupiah(row['nominal'])} • oleh {nama_user(row['dibayar_oleh'])} • {row['tanggal']}",
                parse_mode="HTML",
                reply_markup=aksi_pen_kb(pid)
            )
        else:
            await update.message.reply_text("✅ Pengeluaran diperbarui.", reply_markup=menu_utama())

    elif state == "ep_text_wait":
        pid = ctx.get("pen_id")
        lowered = text.lower()
        nominal_match = re.search(
            r"\b(?:nominal|jumlah|harga|jadi)\s*[:=]?\s*"
            r"(\d{1,3}(?:[.,]\d{3})+|\d+)(?:\s*(rb|ribu|k))?\b",
            lowered,
            re.IGNORECASE,
        )
        if nominal_match:
            value = int(nominal_match.group(1).replace(".", "").replace(",", ""))
            if nominal_match.group(2):
                value *= 1000
            if value <= 0 or value > 1_000_000_000:
                await update.message.reply_text(
                    "Nominal harus antara Rp1 dan Rp1.000.000.000."
                )
                return
            field = "nominal"
        else:
            description_match = re.search(
                r"\b(?:keterangan|ket|deskripsi)\s*[:=]?\s*(.+)$",
                text,
                re.IGNORECASE,
            )
            if not description_match:
                await update.message.reply_text(
                    "Ketik perubahan seperti 'nominal 50000' atau "
                    "'keterangan makan siang'."
                )
                return
            value = description_match.group(1).strip(" :-")
            if not value:
                await update.message.reply_text("Keterangan tidak boleh kosong.")
                return
            field = "keterangan"
        with db() as conn:
            conn.execute(
                f"UPDATE pengeluaran SET {field}=? WHERE id=? AND dihapus=0",
                (value, pid),
            )
        clear_state(uid)
        await update.message.reply_text("✅ Pengeluaran diperbarui.")

    elif state in ("ej_hari_wait", "ep_bayar_wait"):
        await update.message.reply_text(
            "Silakan pilih opsi pada tombol pesan sebelumnya, atau kirim /cancel untuk batal.",
            reply_markup=KB_BATAL
        )

def _day_from_text(text: str) -> int | None:
    lowered = text.lower()
    for index, name in enumerate(HARI):
        if name.lower() in lowered:
            return index
    return None

def _owner_id_from_text(text: str, current_user_id: int) -> int | None:
    lowered = text.lower()
    self_patterns = (
        r"\baku\b",
        r"\bsaya\b",
        r"\bgue\b",
        r"\bgw\b",
        r"\b(?:jadwal|kelas|kuliah|matkul|transaksi|pengeluaran|data|catatan|setting|pengaturan)(?:ku|saya)\b",
        r"\b(?:senin|selasa|rabu|kamis|jumat|sabtu|minggu)(?:ku|saya)\b",
        r"\bhari\s+(?:senin|selasa|rabu|kamis|jumat|sabtu|minggu)\s+(?:aku|saya)\b",
        r"\b(?:punyaku|milikku)\b",
        r"\b(?:milik|punya)\s+(?:aku|saya)\b",
    )
    if any(re.search(pattern, lowered) for pattern in self_patterns):
        return current_user_id
    if any(alias in lowered for alias in ("benaya", "imut")) or USER_A_NAMA.lower() in lowered:
        return USER_A_ID
    if any(alias in lowered for alias in ("agnes", "seng", "agnez")) or USER_B_NAMA.lower() in lowered:
        return USER_B_ID
    return None

async def start_add_jadwal_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(update.effective_user.id, "jf", {"step": "hari", "mode": "add"})
    await update.message.reply_text(
        "📅 <b>Tambah Jadwal</b>\n\nPilih hari:",
        parse_mode="HTML",
        reply_markup=pilih_hari_kb()
    )

async def start_add_pen_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_state(update.effective_user.id, "pf", {"step": "nominal", "mode": "add"})
    await update.message.reply_text(
        "💰 <b>Catat Pengeluaran</b>\n\n"
        "Ketik nominal (contoh: <code>45000</code> atau <code>45.000</code>):",
        parse_mode="HTML",
        reply_markup=KB_BATAL
    )