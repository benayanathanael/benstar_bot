from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from config import HARI

def menu_utama():
    return ReplyKeyboardMarkup(
        [["📅 Jadwal", "💰 Keuangan"],
         ["➕ Tambah", "⚙️ Pengaturan"]],
        resize_keyboard=True,
        is_persistent=True
    )

def pilih_hari_kb(prefix="jf:hari"):
    rows = []
    for i in range(0, 7, 2):
        row = [InlineKeyboardButton(HARI[i], callback_data=f"{prefix}:{i}")]
        if i+1 < 7:
            row.append(InlineKeyboardButton(HARI[i+1], callback_data=f"{prefix}:{i+1}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("❌ Batal", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)

def pilih_bayar_kb():
    from config import USER_A_ID, USER_A_NAMA, USER_B_ID, USER_B_NAMA
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👤 {USER_A_NAMA}", callback_data=f"pf:bayar:{USER_A_ID}")],
        [InlineKeyboardButton(f"👤 {USER_B_NAMA}", callback_data=f"pf:bayar:{USER_B_ID}")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
    ])

def aksi_jadwal_kb(jadwal_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit", callback_data=f"edit_jadwal:{jadwal_id}"),
         InlineKeyboardButton("🗑 Hapus", callback_data=f"del_jadwal:{jadwal_id}")],
    ])

def aksi_pen_kb(pen_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit", callback_data=f"edit_pen:{pen_id}"),
         InlineKeyboardButton("🗑 Hapus", callback_data=f"del_pen:{pen_id}")],
    ])

def edit_field_kb_jadwal(jadwal_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Hari", callback_data=f"ej:{jadwal_id}:hari"),
         InlineKeyboardButton("Jam Mulai", callback_data=f"ej:{jadwal_id}:jam_mulai")],
        [InlineKeyboardButton("Jam Selesai", callback_data=f"ej:{jadwal_id}:jam_selesai"),
         InlineKeyboardButton("Mata Kuliah", callback_data=f"ej:{jadwal_id}:mk")],
        [InlineKeyboardButton("Ruangan", callback_data=f"ej:{jadwal_id}:ruangan")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
    ])

def edit_field_kb_pen(pen_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Nominal", callback_data=f"ep:{pen_id}:nominal"),
         InlineKeyboardButton("Keterangan", callback_data=f"ep:{pen_id}:keterangan")],
        [InlineKeyboardButton("Pembayar", callback_data=f"ep:{pen_id}:bayar")],
        [InlineKeyboardButton("❌ Batal", callback_data="cancel")],
    ])

def nav_jadwal_kb(offset: int):
    back = InlineKeyboardButton("◀️", callback_data=f"nav:{offset-1}")
    home = InlineKeyboardButton("📅 Hari Ini", callback_data="nav:0")
    fwd  = InlineKeyboardButton("▶️", callback_data=f"nav:{offset+1}")
    return InlineKeyboardMarkup([[back, home, fwd]])

def nav_keuangan_kb(offset: int):
    back = InlineKeyboardButton("◀️", callback_data=f"nav_pen:{offset-1}")
    home = InlineKeyboardButton("📅 Minggu Ini", callback_data="nav_pen:0")
    fwd  = InlineKeyboardButton("▶️", callback_data=f"nav_pen:{offset+1}")
    return InlineKeyboardMarkup([[back, home, fwd]])

def tambah_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Jadwal Kuliah", callback_data="add:jadwal")],
        [InlineKeyboardButton("💰 Pengeluaran", callback_data="add:pen")],
    ])

def settings_kb(pref):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'✅' if pref['notif_kelas_self'] else '❌'} Notif kelas (diri sendiri)",
            callback_data="set:tg:self"
        )],
        [InlineKeyboardButton(
            f"{'✅' if pref['notif_kelas_partner'] else '❌'} Notif kelas ke pasangan",
            callback_data="set:tg:partner"
        )],
        [InlineKeyboardButton(
            f"{'✅' if pref['notif_transaksi'] else '❌'} Notif transaksi ke pasangan",
            callback_data="set:tg:trx"
        )],
        [InlineKeyboardButton(
            f"⏰ {pref['menit_sebelum']} menit sebelum kelas",
            callback_data="set:menit"
        )],
    ])

def detail_jadwal_kb(jadwal_ids: list[int]):
    row = []
    for i, jid in enumerate(jadwal_ids):
        row.append(InlineKeyboardButton(f"{i+1}", callback_data=f"detail_jadwal:{jid}"))
    return InlineKeyboardMarkup([row]) if row else None