from telegram import Update
from telegram.ext import ContextTypes
from config import is_valid_user
from keyboards import menu_utama, tambah_menu_kb, menu_edit_kb
from states import get_state, clear_state
from handlers import jadwal, keuangan, settings, add

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
    # 3. NATURAL LANGUAGE ROUTING (Keyword Matching)
    # ==========================================

    # --- INTENT: TAMBAH DATA ---
    if any(k in text_lower for k in ["tambah", "catat", "baru", "input"]):
        if any(k in text_lower for k in ["jadwal", "kuliah", "kelas"]):
            await add.start_add_jadwal_msg(update, context)
        elif any(k in text_lower for k in ["uang", "pengeluaran", "beli", "bayar", "duit", "jajan"]):
            await add.start_add_pen_msg(update, context)
        else:
            await update.message.reply_text(
                "Mau tambah apa nih? Jadwal kuliah atau pengeluaran?",
                reply_markup=tambah_menu_kb()
            )

    # --- INTENT: LIHAT JADWAL ---
    elif any(k in text_lower for k in ["jadwal", "kelas", "kuliah"]):
        await jadwal.show_hari_ini(update, context)

    # --- INTENT: LIHAT KEUANGAN ---
    elif any(k in text_lower for k in ["uang", "keuangan", "pengeluaran", "duit", "bayar", "trx", "transaksi"]):
        await keuangan.show_keuangan(update, context)

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