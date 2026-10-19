import sqlite3
from contextlib import contextmanager
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS preferences (
    user_id INTEGER PRIMARY KEY,
    notif_kelas_self INTEGER DEFAULT 1,
    notif_kelas_partner INTEGER DEFAULT 1,
    notif_transaksi INTEGER DEFAULT 0,
    menit_sebelum INTEGER DEFAULT 15
);

CREATE TABLE IF NOT EXISTS jadwal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    hari INTEGER NOT NULL,
    jam_mulai TEXT NOT NULL,
    jam_selesai TEXT NOT NULL,
    mata_kuliah TEXT NOT NULL,
    dosen TEXT,
    ruangan TEXT,
    aktif INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pengeluaran (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nominal INTEGER NOT NULL,
    keterangan TEXT NOT NULL,
    dibayar_oleh INTEGER NOT NULL,
    tanggal TEXT NOT NULL,
    dihapus INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    user_id INTEGER PRIMARY KEY,
    state TEXT,
    context TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notif_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kunci TEXT UNIQUE NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(jadwal)").fetchall()
        }
        if "dosen" not in columns:
            conn.execute("ALTER TABLE jadwal ADD COLUMN dosen TEXT")
        for uid in (USER_A_ID, USER_B_ID):
            conn.execute(
                "INSERT OR IGNORE INTO preferences (user_id) VALUES (?)", (uid,)
            )

def log_once(kunci: str) -> bool:
    """Insert kunci ke notif_log. Return True jika baru (belum pernah dikirim)."""
    with db() as conn:
        try:
            conn.execute("INSERT INTO notif_log (kunci) VALUES (?)", (kunci,))
            return True
        except sqlite3.IntegrityError:
            return False

# import di sini agar config sudah loaded
from config import USER_A_ID, USER_B_ID