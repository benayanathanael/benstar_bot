import os
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
    import random
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton

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
    app.add_handler(CommandHandler("sync", settings.trigger_sync))
    app.add_handler(CommandHandler("menu", start.start_cmd))
    # Slash Commands (Natural Language)
    app.add_handler(CommandHandler("jadwal", jadwal.show_hari_ini))
    app.add_handler(CommandHandler("uang", keuangan.show_keuangan))
    app.add_handler(CommandHandler("tambah", add.start_add_pen_msg))
    app.add_handler(CommandHandler("setting", settings.show_settings))
    app.add_handler(CommandHandler("cancel", _cancel))
    app.add_handler(CallbackQueryHandler(callback.handle_callback))

    async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
        responses = [
            "🎙️ *Waduh, pesan suaranya masuk!* Tapi maaf ya, aku bot gratisan jadi belum bisa bales pakai suara. 😂\n\nMau aku tarik kode terbaru dari GitHub sekarang?",
            "🎵 *Suara kamu merdu banget!* Sayangnya aku nggak punya telinga buat dengerin. T_T\n\nTapi kalau kamu baru aja selesai ngoding di laptop, pencet tombol di bawah biar aku *update*!",
            "📻 *Sinyal diterima!* Aku udah siap tempur nih. Kamu mau *push* kode baru atau cuma kangen manggil aku?\n\nKalau mau update, klik tombol ini:",
            "🤖 *Bleep bloop!* Aku denger suara kamu, tapi otakku belum bisa nerjemahin bahasa manusia (karena nggak pakai AI berbayar).\n\nYuk, pencet tombol di bawah kalau mau aku *refresh* ke versi paling baru!",
        ]
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "🚀 Ya, Tarik Kode Terbaru!",
                callback_data="trigger_sync_btn",
            )
        ]])
        await update.message.reply_text(
            random.choice(responses),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu.handle_text))

    logging.info("🚀 Benstar running...")
    app.run_polling()

async def _cancel(update, context):
    from states import clear_state
    from keyboards import menu_utama
    clear_state(update.effective_user.id)
    await update.message.reply_text("Dibatalkan.", reply_markup=menu_utama())

if __name__ == "__main__":
    main()