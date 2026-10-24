import os
import logging
from html import escape
import asyncio
import tempfile

# Bersihkan sisa environment variable proxy agar tidak mengganggu koneksi
for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(key, None)

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.request import HTTPXRequest
from config import BOT_TOKEN, is_valid_user
from database import db, init_db
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
    app.add_handler(CommandHandler("sync", settings.trigger_sync))
    app.add_handler(CommandHandler("menu", start.start_cmd))
    # Slash Commands (Natural Language)
    app.add_handler(CommandHandler("jadwal", jadwal.show_hari_ini))
    app.add_handler(CommandHandler("uang", keuangan.show_keuangan))
    app.add_handler(CommandHandler("tambah", add.start_add_pen_msg))
    app.add_handler(CommandHandler("jarvis", jarvis_cmd))
    app.add_handler(CommandHandler("setting", settings.show_settings))
    app.add_handler(CommandHandler("cancel", _cancel))
    app.add_handler(CallbackQueryHandler(callback.handle_callback))

    async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
        from services.audio_parser import transcribe_voice
        from services.ai_parser import parse_expense_with_ai
        from helpers import rupiah

        if not is_valid_user(update.effective_user.id):
            await update.message.reply_text("🚫 Bot private.")
            return

        user_name = escape(update.effective_user.first_name)
        msg = await update.message.reply_text(
            f"🎙️ Menerima transmisi audio, {user_name}. Memproses..."
        )
        try:
            transcript = await transcribe_voice(context, update.message.voice)
            if not transcript:
                await msg.edit_text("❌ Maaf, sensor audio tidak menemukan ucapan yang dapat diproses.")
                return

            await msg.edit_text(
                f"📝 Mendengar: <i>\"{escape(transcript)}\"</i>\n\n"
                "Menganalisis parameter keuangan...",
                parse_mode="HTML",
            )
            expenses = await asyncio.to_thread(parse_expense_with_ai, transcript)
        except Exception:
            logging.exception("Gagal memproses voice note")
            await msg.edit_text("❌ Gagal memproses voice note. Periksa konfigurasi AI lalu coba lagi.")
            return

        if not expenses:
            await msg.edit_text(
                f"🤖 Suara terdeteksi: <i>\"{escape(transcript)}\"</i>\n\n"
                "Namun saya tidak menemukan nominal pengeluaran yang valid.",
                parse_mode="HTML",
            )
            return

        try:
            berhasil = []
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
                            update.effective_user.id,
                            expense["tanggal"],
                        ),
                    )
                    berhasil.append(
                        f"• {escape(expense['keterangan'].title())} "
                        f"({rupiah(expense['nominal'])}) - {expense['tanggal']}"
                    )
        except Exception:
            logging.exception("Gagal menyimpan pengeluaran dari voice note")
            await msg.edit_text("❌ Pengeluaran gagal disimpan. Silakan coba lagi.")
            return

        await msg.edit_text(
            f"✅ <b>Protokol Pencatatan Selesai, {user_name}.</b>\n\n"
            f"Saya telah mencatat {len(expenses)} transaksi:\n"
            f"{chr(10).join(berhasil)}\n\n"
            "Semua data telah diamankan ke dalam database.",
            parse_mode="HTML",
        )

    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu.handle_text))

    logging.info("🚀 Benstar running...")
    app.run_polling()

async def jarvis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_valid_user(update.effective_user.id):
        await update.message.reply_text("🚫 Bot private.")
        return

    user_name = update.effective_user.first_name
    text = " ".join(context.args)
    if not text:
        text = (
            f"Selamat datang kembali, {user_name}. "
            "Sistem Benstar siap menerima perintah Anda."
        )

    message = await update.message.reply_text("🎙️ Menyiapkan pita suara...")
    from services.tts_service import generate_voice

    try:
        with tempfile.TemporaryDirectory(prefix="benstar_tts_") as temp_dir:
            audio_path = os.path.join(temp_dir, "suara_jarvis.ogg")
            voice_path = await generate_voice(text, audio_path)
            if voice_path is None or not os.path.exists(voice_path):
                await message.edit_text("❌ Maaf Tuan, pita suara saya sedang bermasalah.")
                return

            with open(voice_path, "rb") as voice_file:
                await update.message.reply_voice(voice=voice_file)
            try:
                await message.delete()
            except Exception:
                logging.exception("Gagal menghapus status persiapan voice note")
    except Exception:
        logging.exception("Gagal mengirim voice note J.A.R.V.I.S.")
        await message.edit_text("❌ Maaf Tuan, pita suara saya sedang bermasalah.")

async def _cancel(update, context):
    from states import clear_state
    from keyboards import menu_utama
    clear_state(update.effective_user.id)
    await update.message.reply_text("Dibatalkan.", reply_markup=menu_utama())

if __name__ == "__main__":
    main()