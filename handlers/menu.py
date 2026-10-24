import asyncio
import logging
import re
from datetime import timedelta

from telegram import Update
from telegram.ext import ContextTypes
from config import (
    is_valid_user, HARI, nama_user,
    USER_A_ID, USER_B_ID, USER_A_NAMA, USER_B_NAMA,
)
from config import now_wib
from database import db
from keyboards import menu_utama
from states import get_state, clear_state, set_state
from handlers import jadwal, keuangan, settings, add
from helpers import rupiah, esc

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
    if any(alias in lowered for alias in ("benaya", "imut")):
        return USER_A_ID
    if any(alias in lowered for alias in ("agnes", "seng", "agnez")):
        return USER_B_ID
    if len(USER_A_NAMA) > 1 and USER_A_NAMA.lower() in lowered:
        return USER_A_ID
    if len(USER_B_NAMA) > 1 and USER_B_NAMA.lower() in lowered:
        return USER_B_ID
    return None

def _expense_has_keyword(text: str) -> bool:
    if any(
        keyword in text
        for keyword in (
            "uang", "keuangan", "pengeluaran", "duit", "bayar",
            "trx", "transaksi", "belanja",
        )
    ):
        return True
    return bool(
        re.search(r"\b\d{1,3}(?:[.,]\d{3})+(?:\s*(?:rb|ribu|k))?\b|\b\d+(?:\s*(?:rb|ribu|k))\b", text)
        and any(keyword in text for keyword in ("jajan", "makan", "habis", "beli"))
    )

def _expense_number(text: str) -> int | None:
    match = re.search(r"\bnomor\s+(\d+)\b|\bno\.?\s*(\d+)\b", text)
    return int(match.group(1) or match.group(2)) if match else None

def _expense_rows(conn, text: str, owner_id: int | None):
    today = now_wib()
    if "hari ini" in text or "hariini" in text:
        where = "tanggal=?"
        params = [today.strftime("%Y-%m-%d")]
    else:
        start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
        end = (today + timedelta(days=6 - today.weekday())).strftime("%Y-%m-%d")
        where = "tanggal BETWEEN ? AND ?"
        params = [start, end]
    if owner_id is not None:
        where += " AND dibayar_oleh=?"
        params.append(owner_id)
    return conn.execute(
        f"""
        SELECT id, nominal, keterangan, dibayar_oleh, tanggal
        FROM pengeluaran
        WHERE dihapus=0 AND {where}
        ORDER BY tanggal ASC, id ASC
        """,
        params,
    ).fetchall()

def _expense_field_update(text: str):
    nominal_match = re.search(
        r"\b(?:nominal|jumlah|harga|jadi)\s*[:=]?\s*"
        r"(\d{1,3}(?:[.,]\d{3})+|\d+)(?:\s*(?:rb|ribu|k))?\b",
        text,
        re.IGNORECASE,
    )
    if nominal_match:
        value = int(nominal_match.group(1).replace(".", "").replace(",", ""))
        if re.search(r"(?:rb|ribu|k)\b", nominal_match.group(0), re.IGNORECASE):
            value *= 1000
        return "nominal", value
    description_match = re.search(
        r"\b(?:keterangan|ket|deskripsi)\s*[:=]?\s*(.+)$",
        text,
        re.IGNORECASE,
    )
    if description_match:
        return "keterangan", description_match.group(1).strip(" :-")
    return None, None

async def _handle_expense_command(update, context, text_lower, uid):
    owner_id = _owner_id_from_text(text_lower, uid)
    owner_label = nama_user(owner_id) if owner_id is not None else "semua pemilik"
    number = _expense_number(text_lower)
    is_all = any(word in text_lower for word in ("semua", "semuanya", "all"))

    if "hapus" in text_lower or "delete" in text_lower:
        with db() as conn:
            rows = _expense_rows(conn, text_lower, owner_id)
            if is_all:
                ids = [row["id"] for row in rows]
                if ids:
                    conn.execute(
                        f"UPDATE pengeluaran SET dihapus=1 WHERE id IN ({','.join('?' for _ in ids)})",
                        ids,
                    )
        if is_all:
            periode = "hari ini" if "hari ini" in text_lower else "minggu ini"
            await update.message.reply_text(
                f"🗑 {len(rows)} pengeluaran {owner_label} pada {periode} berhasil dihapus."
            )
            return True
        if number is None:
            await update.message.reply_text(
                "Ketik nomor pengeluaran yang mau dihapus, contoh: "
                "'hapus pengeluaran nomor 2'."
            )
            return True
        if number < 1 or number > len(rows):
            await update.message.reply_text(
                f"Nomor pengeluaran tidak valid. Pilih nomor 1 sampai {len(rows)}."
            )
            return True
        selected = rows[number - 1]
        with db() as conn:
            conn.execute(
                "UPDATE pengeluaran SET dihapus=1 WHERE id=? AND dihapus=0",
                (selected["id"],),
            )
        await update.message.reply_text(
            f"🗑 Pengeluaran {owner_label} dihapus:\n"
            f"{selected['keterangan']} ({rupiah(selected['nominal'])})"
        )
        return True

    if any(word in text_lower for word in ("edit", "ubah", "ganti", "rubah", "update")):
        if number is None:
            await update.message.reply_text(
                "Ketik nomor pengeluaran, contoh: 'ubah pengeluaran nomor 2 nominal 50000'."
            )
            return True
        with db() as conn:
            rows = _expense_rows(conn, text_lower, owner_id)
        if number < 1 or number > len(rows):
            await update.message.reply_text(
                f"Nomor pengeluaran tidak valid. Pilih nomor 1 sampai {len(rows)}."
            )
            return True
        field, value = _expense_field_update(text_lower)
        if field is None:
            set_state(uid, "ep_text_wait", {"pen_id": rows[number - 1]["id"]})
            await update.message.reply_text(
                "Mau mengubah nominal atau keterangan?\n"
                "Contoh: 'nominal 50000' atau 'keterangan makan siang'."
            )
            return True
        if field == "nominal" and (value <= 0 or value > 1_000_000_000):
            await update.message.reply_text("Nominal harus antara Rp1 dan Rp1.000.000.000.")
            return True
        if field == "keterangan" and not value:
            await update.message.reply_text("Keterangan tidak boleh kosong.")
            return True
        with db() as conn:
            conn.execute(
                f"UPDATE pengeluaran SET {field}=? WHERE id=? AND dihapus=0",
                (value, rows[number - 1]["id"]),
            )
        await update.message.reply_text(
            f"✅ Pengeluaran nomor {number} diperbarui."
        )
        return True

    return False

async def _handle_legacy_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_valid_user(uid):
        await update.message.reply_text("🚫 Bot private.")
        return

    text = update.message.text.strip()
    text_lower = text.lower()

    # 0. INTENT: UPDATE BOT (Natural Language)
    if any(
        keyword in text_lower
        for keyword in (
            "baruin", "update bot", "tarik kode", "sync", "pull", "restart",
            "refresh", "ngoding", "update", "tarik",
        )
    ):
        await settings.trigger_sync(update, context)
        return

    parsed_schedule_list = add.parse_jadwal_list_text(text)
    explicit_bulk_add = (
        bool(parsed_schedule_list)
        and any(
            marker in text_lower
            for marker in ("tambahkan", "tambah", "buat", "di jadwal")
        )
        and _owner_id_from_text(text_lower, uid) is not None
    )

    if explicit_bulk_add:
        owner_id = _owner_id_from_text(text_lower, uid)
        owner_label = nama_user(owner_id)
        with db() as conn:
            for item in parsed_schedule_list:
                conn.execute("""
                    INSERT INTO jadwal
                        (user_id, hari, jam_mulai, jam_selesai, mata_kuliah, dosen, ruangan)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    owner_id,
                    item["hari"],
                    item["jam_mulai"],
                    item["jam_selesai"],
                    item["matkul"],
                    item["dosen"] or None,
                    item["ruangan"] or None,
                ))
        clear_state(uid)
        await update.message.reply_text(
            f"✅ {len(parsed_schedule_list)} jadwal ditambahkan ke jadwal {owner_label}."
        )
        return

    # 1. ESCAPE HATCH: Jika user menekan tombol menu utama saat di tengah form, reset state!
    if text in ["📅 Jadwal", "💰 Keuangan", "➕ Tambah", "✏️ Edit", "⚙️ Pengaturan"]:
        clear_state(uid)
    else:
        # 2. STATE CHECK: Kalau BUKAN menu utama tapi sedang dalam form (misal isi jam), teruskan ke add.py
        state, ctx = get_state(uid)
        if state:
            await add.handle_flow(update, context, state, ctx)
            return

    # ==========================================
    # 3. INTENT: TAMBAH DATA
    # ==========================================

    # 3a. INTENT: HAPUS JADWAL
    if (
        any(k in text_lower for k in ["hapus", "hapuskan", "hilangkan", "delete"])
        and any(k in text_lower for k in [
            "jadwal", "kelas", "kuliah", "matkul", "mata kuliah",
            "pelajaran", "schedule", "class",
        ])
    ):
        hari = next(
            (index for index, nama in enumerate(HARI) if nama.lower() in text_lower),
            -1,
        )
        owner_id = _owner_id_from_text(text_lower, uid)
        owner_label = None
        if owner_id == USER_A_ID:
            owner_label = USER_A_NAMA
        elif owner_id == USER_B_ID:
            owner_label = USER_B_NAMA

        if any(k in text_lower for k in ["semua", "semuanya", "all"]) and hari != -1:
            with db() as conn:
                if owner_id is None:
                    result = conn.execute(
                        "UPDATE jadwal SET aktif=0 WHERE hari=? AND aktif=1",
                        (hari,),
                    )
                    owner_label = "Benaya dan Agnes"
                else:
                    result = conn.execute(
                        "UPDATE jadwal SET aktif=0 WHERE hari=? AND user_id=? AND aktif=1",
                        (hari, owner_id),
                    )
            await update.message.reply_text(
                f"🗑 {result.rowcount} jadwal {owner_label} pada hari "
                f"{HARI[hari]} berhasil dihapus."
            )
            return

        if hari != -1:
            number_match = re.search(
                r"\b(?:nomor|no\.?)\s+(.+)$",
                text_lower,
            )
            if number_match:
                selected_numbers = sorted(
                    {int(value) for value in re.findall(r"\d+", number_match.group(1))}
                )
                with db() as conn:
                    query = """
                        SELECT id, mata_kuliah, jam_mulai, jam_selesai
                        FROM jadwal
                        WHERE hari=? AND aktif=1
                    """
                    params = [hari]
                    if owner_id is not None:
                        query += " AND user_id=?"
                        params.append(owner_id)
                    rows = conn.execute(
                        query + " ORDER BY jam_mulai, id",
                        params,
                    ).fetchall()

                    invalid_numbers = [
                        number for number in selected_numbers
                        if number < 1 or number > len(rows)
                    ]
                    if invalid_numbers:
                        await update.message.reply_text(
                            f"Nomor jadwal tidak valid: {', '.join(map(str, invalid_numbers))}. "
                            f"Pilih nomor 1 sampai {len(rows)}."
                        )
                        return

                    selected_rows = [rows[number - 1] for number in selected_numbers]
                    conn.executemany(
                        "UPDATE jadwal SET aktif=0 WHERE id=? AND aktif=1",
                        [(row["id"],) for row in selected_rows],
                    )

                deleted_lines = "\n".join(
                    f"• {row['mata_kuliah']} ({row['jam_mulai']}-{row['jam_selesai']})"
                    for row in selected_rows
                )
                target = owner_label or "semua pemilik"
                await update.message.reply_text(
                    f"🗑 {len(selected_rows)} jadwal {target} hari {HARI[hari]} dihapus "
                    "otomatis:\n" + deleted_lines
                )
                return

            if owner_id is not None:
                await jadwal.show_delete_jadwal_day(
                    update,
                    context,
                    hari,
                    owner_id=owner_id,
                )
            else:
                await update.message.reply_text(
                    "Ketik nomor jadwal yang mau dihapus, contoh: "
                    "'hapus matkul hari Senin nomor 1 dan 2'."
                )
            return

        if any(k in text_lower for k in ["semua", "semuanya", "all"]) and hari != -1:
            if owner_id is not None:
                with db() as conn:
                    rows = conn.execute(
                        """
                        SELECT mata_kuliah, jam_mulai, jam_selesai
                        FROM jadwal
                        WHERE hari=? AND user_id=? AND aktif=1
                        ORDER BY jam_mulai
                        """,
                        (hari, owner_id),
                    ).fetchall()
                if not rows:
                    await update.message.reply_text(
                        f"Tidak ada jadwal {owner_label} pada hari {HARI[hari]}."
                    )
                    return
                daftar = "\n".join(
                    f"• {row['jam_mulai']}-{row['jam_selesai']} "
                    f"{esc(row['mata_kuliah'])}"
                    for row in rows
                )
                await update.message.reply_text(
                    f"<b>Konfirmasi hapus semua jadwal</b>\n\n"
                    f"Pemilik: {esc(owner_label)}\n"
                    f"Hari: {HARI[hari]}\n\n{daftar}\n\n"
                    "Yakin ingin menghapus semuanya?",
                    parse_mode="HTML",
                )
                return

        if hari == -1:
            await update.message.reply_text(
                "Ketik hari jadwal yang mau dihapus: Senin, Selasa, Rabu, Kamis, Jumat, Sabtu, atau Minggu."
            )
        else:
            await jadwal.show_delete_jadwal_day(update, context, hari)
        return

    # 3b. INTENT: PENGELUARAN BERBASIS TEKS
    has_expense_word = any(
        keyword in text_lower
        for keyword in ("jajan", "beli", "makan", "bayar", "habis", "lupa")
    )
    mentions_schedule = any(
        keyword in text_lower
        for keyword in ("jadwal", "kuliah", "kelas", "matkul", "mata kuliah")
    )
    if _expense_has_keyword(text_lower) or (has_expense_word and not mentions_schedule):
        if await _handle_expense_command(update, context, text_lower, uid):
            return

        await update.message.reply_text("🧠 Menganalisis teks...")
        try:
            from services.ai_parser import parse_expense_with_ai
            expenses = await asyncio.to_thread(parse_expense_with_ai, text)
        except Exception:
            logging.exception("Gagal menganalisis pengeluaran teks")
            await update.message.reply_text(
                "❌ Gagal menganalisis pengeluaran. Periksa konfigurasi AI lalu coba lagi."
            )
            return

        if not expenses:
            await add.start_add_pen_msg(update, context)
            return

        owner_id = _owner_id_from_text(text_lower, uid) or uid
        try:
            lines = []
            with db() as conn:
                for expense in expenses:
                    conn.execute(
                        """
                        INSERT INTO pengeluaran
                            (nominal, keterangan, dibayar_oleh, tanggal)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            expense["nominal"],
                            expense["keterangan"],
                            owner_id,
                            expense["tanggal"],
                        ),
                    )
                    lines.append(
                        f"• {esc(expense['keterangan'].title())} "
                        f"({rupiah(expense['nominal'])}) - {expense['tanggal']}"
                    )
        except Exception:
            logging.exception("Gagal menyimpan pengeluaran teks")
            await update.message.reply_text(
                "❌ Pengeluaran gagal disimpan. Silakan coba lagi."
            )
            return
        await update.message.reply_text(
            f"✅ <b>Protokol Pencatatan Selesai.</b>\n\n"
            f"Saya mencatat {len(expenses)} transaksi untuk "
            f"{esc(nama_user(owner_id))}:\n{chr(10).join(lines)}",
            parse_mode="HTML",
        )
        return

    if parsed_schedule_list or any(k in text_lower for k in ["nambah", "tambah", "tambahin", "bikin", "buat", "catat", "input", "lupa", "catet"]):
        if parsed_schedule_list or any(k in text_lower for k in [
            "jadwal", "kuliah", "kelas", "matkul", "mata kuliah",
            "pelajaran", "schedule", "class",
        ]):
            parsed_list = parsed_schedule_list
            if parsed_list:
                owner_id = _owner_id_from_text(text_lower, uid)
                owner_label = None
                if owner_id == USER_A_ID:
                    owner_label = USER_A_NAMA
                elif owner_id == USER_B_ID:
                    owner_label = USER_B_NAMA

                if owner_id is not None and any(
                    marker in text_lower
                    for marker in ("tambahkan", "tambahkan", "tambah", "buat", "di jadwal")
                ):
                    with db() as conn:
                        for item in parsed_list:
                            conn.execute("""
                                INSERT INTO jadwal
                                    (user_id, hari, jam_mulai, jam_selesai, mata_kuliah, dosen, ruangan)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                owner_id,
                                item["hari"],
                                item["jam_mulai"],
                                item["jam_selesai"],
                                item["matkul"],
                                item["dosen"] or None,
                                item["ruangan"] or None,
                            ))
                    await update.message.reply_text(
                        f"✅ {len(parsed_list)} jadwal ditambahkan ke jadwal {owner_label}.",
                    )
                    return

                set_state(uid, "bulk_jadwal_action", {"items": parsed_list})
                preview = "\n\n".join(
                    f"<b>{HARI[item['hari']]} {item['jam_mulai']}-{item['jam_selesai']}</b>\n"
                    f"Matkul : {item['matkul']}\n"
                    f"Dosen : {item['dosen'] or '-'}"
                    for item in parsed_list
                )
                await update.message.reply_text(
                    f"Data jadwal terbaca ({len(parsed_list)} jadwal):\n\n{preview}\n\n"
                    "Ketik 'simpan semua', 'edit jadwal', 'hapus jadwal', atau 'batal'.",
                    parse_mode="HTML",
                )
                return

            parsed = add.parse_jadwal_text(text)

            if parsed and parsed["jam_mulai"]:
                if parsed["hari"] != -1:
                    set_state(uid, "jf_nl_owner", parsed)
                    await update.message.reply_text(
                        f"Data jadwal terbaca:\n"
                        f"📅 {HARI[parsed['hari']]} "
                        f"{parsed['jam_mulai']}-{parsed['jam_selesai']}\n"
                        f"📚 {parsed['matkul']}\n\n"
                        "Ketik pemilik jadwal: Benaya atau Agnes.",
                    )
                else:
                    set_state(uid, "jf_nl_hari", parsed)
                    await update.message.reply_text(
                        f"Data terbaca! Tapi ini hari apa?\n"
                        f"(Matkul: {parsed['matkul']}, Jam: {parsed['jam_mulai']}-{parsed['jam_selesai']})\n"
                        "Ketik nama harinya.",
                    )
                return

            await add.start_add_jadwal_msg(update, context)
            return
        elif any(k in text_lower for k in ["uang", "pengeluaran", "beli", "bayar", "duit", "jajan", "makan", "habis"]):
            await update.message.reply_text("🧠 Menganalisis teks...")
            try:
                from services.ai_parser import parse_expense_with_ai
                expenses = await asyncio.to_thread(parse_expense_with_ai, text)
            except Exception:
                logging.exception("Gagal menganalisis pengeluaran teks")
                await update.message.reply_text(
                    "❌ Gagal menganalisis pengeluaran. Periksa konfigurasi AI lalu coba lagi."
                )
                return

            if not expenses:
                await add.start_add_pen_msg(update, context)
                return

            try:
                lines = []
                with db() as conn:
                    for expense in expenses:
                        conn.execute(
                            """
                            INSERT INTO pengeluaran (nominal, keterangan, dibayar_oleh, tanggal)
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                expense["nominal"],
                                expense["keterangan"],
                                uid,
                                expense["tanggal"],
                            ),
                        )
                        lines.append(
                            f"• {esc(expense['keterangan'].title())} "
                            f"({rupiah(expense['nominal'])}) - {expense['tanggal']}"
                        )
            except Exception:
                logging.exception("Gagal menyimpan pengeluaran teks")
                await update.message.reply_text(
                    "❌ Pengeluaran gagal disimpan. Silakan coba lagi."
                )
                return
            await update.message.reply_text(
                f"✅ <b>Protokol Pencatatan Selesai.</b>\n\n"
                f"Saya mencatat {len(expenses)} transaksi:\n{chr(10).join(lines)}",
                parse_mode="HTML",
            )
            return
        else:
            await update.message.reply_text(
                "Ketik 'tambah jadwal' atau 'tambah pengeluaran'."
            )
            return

    # 4. INTENT: EDIT DATA
    elif any(k in text_lower for k in [
        "edit", "editi", "editin", "editkan", "mau edit",
        "ubah", "ubahin", "ubahakan", "rubah", "ganti", "gantikan",
        "revisi", "perbaiki", "perbaikan", "koreksi", "update", "salah",
    ]):
        if any(k in text_lower for k in [
            "jadwal", "kelas", "kuliah", "matkul", "mata kuliah",
            "pelajaran", "schedule", "class",
        ]):
            hari = next(
                (index for index, nama in enumerate(HARI) if nama.lower() in text_lower),
                -1,
            )
            if hari == -1:
                await jadwal.show_edit_jadwal_list(update, context)
            else:
                await jadwal.show_edit_jadwal_day(update, context, hari)
        elif any(k in text_lower for k in [
            "uang", "keuangan", "pengeluaran", "duit", "bayar",
            "trx", "transaksi", "nominal", "belanja",
        ]):
            await keuangan.show_edit_keuangan_list(update, context)
        else:
            await update.message.reply_text(
                "Ketik 'edit jadwal' atau 'edit keuangan'.",
            )
        return

    # 5. INTENT: LIHAT JADWAL (Dengan deteksi hari)
    elif any(k in text_lower for k in [
        "lihat", "cek", "buka", "tampil", "jadwal", "kelas", "kuliah",
        "matkul", "mata kuliah", "pelajaran", "schedule", "class",
    ]):
        hari_map = {
            "senin": 0,
            "selasa": 1,
            "rabu": 2,
            "kamis": 3,
            "jumat": 4,
            "sabtu": 5,
            "minggu": 6,
        }
        target_hari = next(
            (hari_idx for hari_name, hari_idx in hari_map.items() if hari_name in text_lower),
            -1,
        )
        owner_id = _owner_id_from_text(text_lower, uid)

        if any(k in text_lower for k in ["semua", "seluruh", "minggu ini", "sampai terakhir"]):
            await jadwal.show_semua_jadwal(update, context, owner_id=owner_id)
        elif target_hari != -1:
            await jadwal.show_jadwal_by_hari(update, context, target_hari)
        else:
            await jadwal.show_hari_ini(update, context, owner_id=owner_id)
        return

    # 6. INTENT: LIHAT KEUANGAN
    elif any(k in text_lower for k in ["uang", "keuangan", "pengeluaran", "duit", "bayar", "trx", "transaksi"]):
        await keuangan.show_keuangan(update, context)
        return

    # 7. INTENT: PENGATURAN
    elif any(k in text_lower for k in ["setting", "pengaturan", "notif", "preferensi"]):
        await settings.show_settings(update, context)

    # ==========================================
    # 8. TOMBOL REPLY KEYBOARD (Persistent Menu)
    # ==========================================
    elif text == "📅 Jadwal":
        await jadwal.show_hari_ini(update, context)
    elif text == "💰 Keuangan":
        await keuangan.show_keuangan(update, context)
    elif text == "➕ Tambah":
        await update.message.reply_text("Ketik 'tambah jadwal' atau 'tambah pengeluaran'.")
    elif text == "✏️ Edit":
        await update.message.reply_text("Ketik 'edit jadwal' atau 'edit keuangan'.")
    elif text == "⚙️ Pengaturan":
        await settings.show_settings(update, context)

    # ==========================================
    # 9. FALLBACK (Kalau bot nggak ngerti)
    # ==========================================
    else:
        await update.message.reply_text(
            f"Hmm, aku belum ngerti maksud \"{text}\".\n\n"
            "Kamu bisa ngetik perintah kayak:\n"
            "• <i>\"tambah jadwal\"</i>\n"
            "• <i>\"lihat keuangan\"</i>\n"
            "• Atau pakai menu di bawah ya 👇",
            parse_mode="HTML",
        )


async def _handle_ai_intent(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    from services.ai_parser import parse_natural_language

    try:
        result = await asyncio.to_thread(parse_natural_language, text)
    except Exception:
        logging.exception("Gagal memahami pesan bebas")
        await update.message.reply_text(
            "❌ Maaf Tuan, pesan belum dapat dipahami. Silakan coba lagi."
        )
        return

    intent = result["intent"]
    data = result["data"]
    reply_text = result["reply_text"]
    if result["kekurangan"]:
        await update.message.reply_text(reply_text)
        return

    try:
        if intent == "tambah_jadwal":
            schedules = data["jadwal"]
            owner_id = _owner_id_from_text(str(data.get("pemilik", "Saya")), update.effective_user.id)
            if owner_id is None:
                await update.message.reply_text("Tuan, jadwal ini untuk siapa?")
                return
            with db() as conn:
                for schedule in schedules:
                    conn.execute(
                        """
                        INSERT INTO jadwal
                            (user_id, hari, jam_mulai, jam_selesai, mata_kuliah, dosen, ruangan)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            owner_id,
                            schedule["hari"],
                            schedule["jam_mulai"],
                            schedule["jam_selesai"],
                            schedule["mata_kuliah"],
                            schedule.get("dosen") or None,
                            schedule.get("ruangan") or None,
                        ),
                    )
            await update.message.reply_text(reply_text)
        elif intent == "tambah_pengeluaran":
            payer = str(data.get("dibayar_oleh", "Saya"))
            payer_id = _owner_id_from_text(payer, update.effective_user.id) or update.effective_user.id
            with db() as conn:
                conn.execute(
                    """
                    INSERT INTO pengeluaran (nominal, keterangan, dibayar_oleh, tanggal)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        data["nominal"],
                        data["keterangan"],
                        payer_id,
                        data["tanggal"],
                    ),
                )
            await update.message.reply_text(reply_text)
        elif intent == "lihat_jadwal":
            await update.message.reply_text(reply_text)
            period = data.get("periode", "hari")
            if period in ("minggu", "semua"):
                await jadwal.show_semua_jadwal(update, context)
            else:
                day = data.get("hari", now_wib().weekday())
                await jadwal.show_jadwal_by_hari(update, context, day)
        elif intent == "lihat_keuangan":
            await update.message.reply_text(reply_text)
            await keuangan.show_keuangan(
                update,
                context,
                period=data.get("periode", "minggu_ini"),
            )
        else:
            await update.message.reply_text(reply_text)
    except Exception:
        logging.exception("Gagal menjalankan intent %s", intent)
        await update.message.reply_text(
            "Mohon maaf, Tuan. Terjadi kendala saat memproses permintaan Anda."
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    uid = update.effective_user.id
    if not is_valid_user(uid):
        await update.message.reply_text("🚫 Bot private.")
        return

    text = update.message.text.strip()
    text_lower = text.lower()
    if text in {"📅 Jadwal", "💰 Keuangan", "➕ Tambah", "✏️ Edit", "⚙️ Pengaturan"}:
        clear_state(uid)
        if text == "📅 Jadwal":
            await jadwal.show_hari_ini(update, context)
        elif text == "💰 Keuangan":
            await keuangan.show_keuangan(update, context)
        elif text == "➕ Tambah":
            await update.message.reply_text(
                "Ketik 'tambah jadwal' atau 'tambah pengeluaran'."
            )
        elif text == "✏️ Edit":
            await update.message.reply_text("Ketik 'edit jadwal' atau 'edit keuangan'.")
        else:
            await settings.show_settings(update, context)
        return

    state, ctx = get_state(uid)
    if state:
        await add.handle_flow(update, context, state, ctx)
        return

    if add.parse_jadwal_list_text(text):
        await _handle_legacy_text(update, context)
        return

    sync_words = (
        "baruin", "update bot", "tarik kode", "sync", "pull", "restart",
        "refresh", "ngoding", "update", "tarik",
    )
    delete_words = ("hapus", "hapuskan", "hilangkan", "delete")
    schedule_words = (
        "jadwal", "kelas", "kuliah", "matkul", "mata kuliah",
        "pelajaran", "schedule", "class",
    )
    edit_words = (
        "edit", "editi", "editin", "editkan", "mau edit", "ubah", "ubahin",
        "ubahakan", "rubah", "ganti", "gantikan", "revisi", "perbaiki",
        "perbaikan", "koreksi", "salah",
    )
    settings_words = ("setting", "pengaturan", "notif", "preferensi")
    if (
        any(word in text_lower for word in sync_words)
        or (
            any(word in text_lower for word in delete_words)
            and any(word in text_lower for word in schedule_words)
        )
        or any(word in text_lower for word in edit_words)
        or any(word in text_lower for word in settings_words)
        or (
            _expense_has_keyword(text_lower)
            and any(word in text_lower for word in (*delete_words, *edit_words))
        )
    ):
        await _handle_legacy_text(update, context)
        return

    await _handle_ai_intent(update, context, text)