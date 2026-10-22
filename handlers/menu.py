from telegram import Update
from telegram.ext import ContextTypes
from config import is_valid_user, HARI, nama_user
from database import db
from keyboards import (
    menu_utama, tambah_menu_kb, menu_edit_kb, pilih_hari_kb,
    pilih_pemilik_jadwal_kb,
)
from states import get_state, clear_state, set_state
from handlers import jadwal, keuangan, settings, add
from helpers import rupiah

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_valid_user(uid):
        await update.message.reply_text("🚫 Bot private.")
        return

    text = update.message.text.strip()
    text_lower = text.lower()

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
        and any(k in text_lower for k in ["jadwal", "kelas", "kuliah"])
    ):
        hari = next(
            (index for index, nama in enumerate(HARI) if nama.lower() in text_lower),
            -1,
        )
        if hari == -1:
            await update.message.reply_text(
                "Pilih hari jadwal yang mau dihapus:",
                reply_markup=pilih_hari_kb(prefix="del_nl"),
            )
        else:
            await jadwal.show_delete_jadwal_day(update, context, hari)
        return

    if any(k in text_lower for k in ["nambah", "tambah", "tambahin", "bikin", "buat", "catat", "input", "lupa", "catet"]):
        if any(k in text_lower for k in ["jadwal", "kuliah", "kelas", "matkul", "mata kuliah"]):
            parsed = add.parse_jadwal_text(text)

            if parsed and parsed["jam_mulai"]:
                if parsed["hari"] != -1:
                    set_state(uid, "jf_nl_owner", parsed)
                    await update.message.reply_text(
                        f"Data jadwal terbaca:\n"
                        f"📅 {HARI[parsed['hari']]} "
                        f"{parsed['jam_mulai']}-{parsed['jam_selesai']}\n"
                        f"📚 {parsed['matkul']}\n\n"
                        "Jadwal ini untuk siapa?",
                        reply_markup=pilih_pemilik_jadwal_kb(),
                    )
                else:
                    set_state(uid, "jf_nl_hari", parsed)
                    await update.message.reply_text(
                        f"Data terbaca! Tapi ini hari apa?\n"
                        f"(Matkul: {parsed['matkul']}, Jam: {parsed['jam_mulai']}-{parsed['jam_selesai']})",
                        reply_markup=pilih_hari_kb(prefix="jf_nl"),
                    )
                return

            await add.start_add_jadwal_msg(update, context)
            return
        elif any(k in text_lower for k in ["uang", "pengeluaran", "beli", "bayar", "duit", "jajan", "makan", "habis"]):
            parsed = add.parse_pen_text(text)
            if parsed:
                with db() as conn:
                    conn.execute("""
                        INSERT INTO pengeluaran (nominal, keterangan, dibayar_oleh, tanggal)
                        VALUES (?, ?, ?, ?)
                    """, (parsed["nominal"], parsed["keterangan"], uid, parsed["tanggal"]))

                await update.message.reply_text(
                    f"✅ <b>Pengeluaran Otomatis Tersimpan!</b>\n\n"
                    f"🧾 Keterangan: <b>{parsed['keterangan'].title()}</b>\n"
                    f"💰 Nominal: {rupiah(parsed['nominal'])}\n"
                    f"📅 Tanggal: {parsed['tanggal']}\n"
                    f"👤 Pembayar: {nama_user(uid)}",
                    parse_mode="HTML",
                    reply_markup=menu_utama(),
                )
            else:
                await add.start_add_pen_msg(update, context)
            return
        else:
            await update.message.reply_text(
                "Mau tambah apa nih? Jadwal kuliah atau pengeluaran?",
                reply_markup=tambah_menu_kb()
            )
            return

    # 4. INTENT: LIHAT JADWAL
    elif any(k in text_lower for k in ["lihat", "cek", "buka", "tampil", "jadwal", "kelas", "kuliah"]):
        hari = next(
            (index for index, nama in enumerate(HARI) if nama.lower() in text_lower),
            -1,
        )
        if hari == -1:
            await jadwal.show_hari_ini(update, context)
        else:
            await jadwal.show_hari(update, context, hari)
        return

    # 5. INTENT: LIHAT KEUANGAN
    elif any(k in text_lower for k in ["uang", "keuangan", "pengeluaran", "duit", "bayar", "trx", "transaksi"]):
        await keuangan.show_keuangan(update, context)
        return

    # --- INTENT: EDIT DATA ---
    elif any(k in text_lower for k in ["edit", "ubah", "ganti", "revisi", "salah"]):
        await update.message.reply_text("Pilih data yang mau diedit:", reply_markup=menu_edit_kb())

    # --- INTENT: PENGATURAN ---
    elif any(k in text_lower for k in ["setting", "pengaturan", "notif", "preferensi"]):
        await settings.show_settings(update, context)

    # ==========================================
    # 4. TOMBOL REPLY KEYBOARD (Persistent Menu)
    # ==========================================
    elif text == "📅 Jadwal":
        await jadwal.show_hari_ini(update, context)
    elif text == "💰 Keuangan":
        await keuangan.show_keuangan(update, context)
    elif text == "➕ Tambah":
        await update.message.reply_text("Mau tambah apa?", reply_markup=tambah_menu_kb())
    elif text == "✏️ Edit":
        await update.message.reply_text("Pilih data yang mau diedit:", reply_markup=menu_edit_kb())
    elif text == "⚙️ Pengaturan":
        await settings.show_settings(update, context)

    # ==========================================
    # 5. FALLBACK (Kalau bot nggak ngerti)
    # ==========================================
    else:
        await update.message.reply_text(
            f"Hmm, aku belum ngerti maksud \"{text}\".\n\n"
            "Kamu bisa ngetik perintah kayak:\n"
            "• <i>\"tambah jadwal\"</i>\n"
            "• <i>\"lihat keuangan\"</i>\n"
            "• Atau pakai menu di bawah ya 👇",
            parse_mode="HTML",
            reply_markup=menu_utama()
        )