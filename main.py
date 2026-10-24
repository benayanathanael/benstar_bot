import os
import sys
import subprocess
import logging

# Bersihkan sisa environment variable proxy agar tidak mengganggu koneksi
for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(key, None)

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.request import HTTPXRequest
from config import BOT_TOKEN
from database import init_db
from handlers import start, menu, callback, jadwal, keuangan, add, settings
from services.scheduler import start_scheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

async def _post_init(app):
    start_scheduler(app.bot)

def main():
    init_db()
    request = HTTPXRequest(httpx_kwargs={"trust_env": False})
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(_post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start.start_cmd))
    app.add_handler(CommandHandler("sync", sync_cmd))
    app.add_handler(CommandHandler("menu", start.start_cmd))
    # Slash Commands (Natural Language)
    app.add_handler(CommandHandler("jadwal", jadwal.show_hari_ini))
    app.add_handler(CommandHandler("uang", keuangan.show_keuangan))
    app.add_handler(CommandHandler("tambah", add.start_add_pen_msg))
    app.add_handler(CommandHandler("setting", settings.show_settings))
    app.add_handler(CommandHandler("cancel", _cancel))
    app.add_handler(CallbackQueryHandler(callback.handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu.handle_text))

    logging.info("🚀 Benstar running...")
    app.run_polling()

async def sync_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import USER_A_ID, USER_B_ID
    uid = update.effective_user.id
    if uid not in (USER_A_ID, USER_B_ID):
        return

    msg = await update.message.reply_text("🔄 Menarik update terbaru dari GitHub...")

    try:
        subprocess.run(["git", "fetch", "--all"], check=True, capture_output=True)
        subprocess.run(["git", "reset", "--hard", "origin/main"], check=True, capture_output=True)

        await msg.edit_text("✅ Update berhasil! Bot sedang restart...")
        os._exit(0)
    except Exception as e:
        await msg.edit_text(f"❌ Gagal update: {e}")

async def _cancel(update, context):
    from states import clear_state
    from keyboards import menu_utama
    clear_state(update.effective_user.id)
    await update.message.reply_text("Dibatalkan.", reply_markup=menu_utama())

if __name__ == "__main__":
    main()