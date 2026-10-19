import html
import re
from config import HARI, BULAN, now_wib

def esc(s: str) -> str:
    return html.escape(str(s))

def valid_jam(s: str) -> str | None:
    s = s.strip()
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", s)
    if not m: return None
    h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h < 24 and 0 <= mi < 60:
        return f"{h:02d}:{mi:02d}"
    return None

def valid_nominal(s: str) -> int | None:
    s = s.strip().replace(".", "").replace(",", "").replace(" ", "")
    if s.isdigit():
        n = int(s)
        if 0 < n <= 1_000_000_000:
            return n
    return None

def rupiah(n: int) -> str:
    return f"Rp {n:,}".replace(",", ".")

def tanggal_indo(d) -> str:
    return f"{d.day} {BULAN[d.month-1]} {d.year}"

def hari_indo(h: int) -> str:
    return HARI[h]

def tanggal_hari_ini() -> str:
    return now_wib().strftime("%Y-%m-%d")

def bulan_ini() -> str:
    return now_wib().strftime("%Y-%m")