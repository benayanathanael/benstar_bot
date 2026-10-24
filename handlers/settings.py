import os
import subprocess

from telegram import Update
from telegram.ext import ContextTypes
from config import nama_user, partner_id, USER_A_ID, USER_B_ID
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

async def trigger_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in (USER_A_ID, USER_B_ID):
        return

    if update.message:
        msg = await update.message.reply_text("🔄 Menarik update terbaru dari GitHub...")
    elif update.callback_query:
        msg = await update.callback_query.edit_message_text(
            "🔄 Menarik update terbaru dari GitHub..."
        )
    else:
        raise ValueError("Sync requires a message or callback query.")

    try:
        subprocess.run(["git", "fetch", "--all"], check=True, capture_output=True)
        subprocess.run(
            ["git", "reset", "--hard", "origin/main"],
            check=True,
            capture_output=True,
        )
        await msg.edit_text("✅ Update berhasil! Bot sedang restart...")
        os._exit(0)
    except Exception as e:
        await msg.edit_text(f"❌ Gagal update: {e}")