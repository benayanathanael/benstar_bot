import asyncio
import logging
import os
import tempfile

import edge_tts

logger = logging.getLogger(__name__)


async def generate_voice(
    text: str,
    filename: str = "suara_jarvis.ogg",
) -> str | None:
    mp3_fd, mp3_file = tempfile.mkstemp(suffix=".mp3")
    os.close(mp3_fd)
    try:
        communicate = edge_tts.Communicate(text, "id-ID-ArdiNeural")
        await communicate.save(mp3_file)
        await asyncio.to_thread(_convert_to_ogg, mp3_file, filename)
        return filename
    except Exception:
        logger.exception("Gagal membuat voice note TTS")
        try:
            os.remove(filename)
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("Gagal membersihkan file OGG yang tidak lengkap", exc_info=True)
        return None
    finally:
        try:
            os.remove(mp3_file)
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("Gagal menghapus file MP3 sementara", exc_info=True)


def _convert_to_ogg(mp3_file: str, filename: str) -> None:
    import imageio_ffmpeg
    from pydub import AudioSegment

    AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
    audio = AudioSegment.from_file(mp3_file, format="mp3", codec="mp3")
    audio.export(filename, format="ogg", codec="libopus")
