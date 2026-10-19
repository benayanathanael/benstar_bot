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

    # ESCAPE HATCH: Jika user menekan menu utama saat di tengah form, reset!
    if text in ["📅 Jadwal", "💰 Keuangan", "➕ Tambah", "✏️ Edit", "⚙️ Pengaturan"]:
        clear_state(uid)
    else:
        # Kalau BUKAN menu utama, cek apakah sedang dalam form
        state, ctx = get_state(uid)
        if state:
            await add.handle_flow(update, context, state, ctx)
            return

    # Menu Navigasi Utama
    if text == "📅 Jadwal":
        await jadwal.show_hari_ini(update, context)
    elif text == "💰 Keuangan":
        await keuangan.show_keuangan(update, context)
    elif text == "➕ Tambah":
        await update.message.reply_text(
            "Mau tambah apa?",
            reply_markup=tambah_menu_kb()
        )
    elif text == "✏️ Edit":
        await update.message.reply_text(
            "Pilih data yang mau diedit:",
            reply_markup=menu_edit_kb()
        )
    elif text == "⚙️ Pengaturan":
        await settings.show_settings(update, context)
    else:
        await update.message.reply_text(
            "Gunakan menu di bawah ya 😊",
            reply_markup=menu_utama()
        )