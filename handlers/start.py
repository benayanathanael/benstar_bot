from telegram import Update
from telegram.ext import ContextTypes
from config import is_valid_user, nama_user, partner_id
from keyboards import menu_utama

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_valid_user(uid):
        await update.message.reply_text(
            "🚫 Maaf, bot ini private.\n"
            "Hanya untuk dua orang yang terdaftar."
        )
        return
    pasangan = nama_user(partner_id(uid))
    await update.message.reply_text(
        f"👋 Halo <b>{nama_user(uid)}</b>!\n\n"
        f"Selamat datang di <b>Benstar</b>.\n"
        f"Pasangan kamu: <b>{pasangan}</b>\n\n"
        f"Gunakan menu di bawah untuk mulai.",
        parse_mode="HTML",
        reply_markup=menu_utama()
    )