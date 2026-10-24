import asyncio

from groq import Groq

from config import GROQ_API_KEY

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


async def transcribe_voice(context, voice) -> str:
    if client is None:
        raise RuntimeError("GROQ_API_KEY belum dikonfigurasi.")

    telegram_file = await context.bot.get_file(voice.file_id)
    audio = bytes(await telegram_file.download_as_bytearray())
    if not audio:
        raise ValueError("File voice note kosong.")
    if len(audio) > 25 * 1024 * 1024:
        raise ValueError("Ukuran voice note melebihi batas transkripsi 25 MB.")

    transcription = await asyncio.to_thread(
        client.audio.transcriptions.create,
        file=("voice.ogg", audio),
        model="whisper-large-v3-turbo",
        response_format="text",
        language="id",
    )
    transcript = transcription if isinstance(transcription, str) else transcription.text
    return transcript.strip()
