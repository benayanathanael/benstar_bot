from telegram import Update
from telegram.ext import ContextTypes
from config import nama_user, partner_id
from database import db
from keyboards import settings_kb

def _settings_text(uid, pref):
    return (
        f"⚙️ <b>Pengaturan</b>\n\n"
        f"👥 Pasangan: <b>{nama_user(partner_id(uid))}</b>\n\n"
        f"<i>Klik tombol untuk toggle. Perubahan langsung tersimpan.</i>"
    )

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    with db() as conn:
        pref = conn.execute(
            "SELECT * FROM preferences WHERE user_id=?", (uid,)
        ).fetchone()
    if not pref:
        return
    await update.message.reply_text(
        _settings_text(uid, pref),
        parse_mode="HTML",
        reply_markup=settings_kb(pref)
    )