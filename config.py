import os
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN    = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
USER_A_ID    = int(os.getenv("USER_A_ID", "0"))
USER_B_ID    = int(os.getenv("USER_B_ID", "0"))
USER_A_NAMA  = os.getenv("USER_A_NAMA", "A")
USER_B_NAMA  = os.getenv("USER_B_NAMA", "B")
DB_PATH      = "benstar.db"
TZ           = ZoneInfo("Asia/Jakarta")

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
         "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

def now_wib():
    return datetime.now(TZ)

def nama_user(user_id: int | None) -> str:
    if user_id == USER_A_ID: return USER_A_NAMA
    if user_id == USER_B_ID: return USER_B_NAMA
    return "?"

def partner_id(user_id: int) -> int | None:
    if user_id == USER_A_ID: return USER_B_ID
    if user_id == USER_B_ID: return USER_A_ID
    return None

def is_valid_user(user_id: int) -> bool:
    return user_id in (USER_A_ID, USER_B_ID)