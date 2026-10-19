from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from config import HARI, nama_user, USER_A_ID, USER_B_ID, now_wib
from database import db
from helpers import hari_indo, esc
from keyboards import nav_jadwal_kb

def _jadwal_info(mata_kuliah: str, dosen: str | None = None) -> tuple[str, str | None]:
    if dosen:
        return str(mata_kuliah).strip(), str(dosen).strip() or None
    parts = str(mata_kuliah).split(" � ", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip() or None
    return str(mata_kuliah).strip(), None

async def show_hari_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _render_jadwal(update, context, offset=0, edit_mode=False, is_edit_list=False)

async def show_edit_jadwal_list(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0):
    await _render_jadwal(
        update,
        context,
        offset=offset,
        edit_mode=bool(update.callback_query),
        is_edit_list=True,
    )

async def show_delete_jadwal_list(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0):
    await _render_jadwal(
        update,
        context,
        offset=offset,
        edit_mode=bool(update.callback_query),
        is_edit_list=True,
        delete_mode=True,
    )

async def _render_jadwal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    offset: int,
    edit_mode: bool,
    is_edit_list: bool,
    delete_mode: bool = False,
):
    hari = (now_wib().weekday() + offset) % 7

    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM jadwal WHERE hari=? AND aktif=1 ORDER BY jam_mulai",
            (hari,)
        ).fetchall()

    jadwal_a = [r for r in rows if r["user_id"] == USER_A_ID]
    jadwal_b = [r for r in rows if r["user_id"] == USER_B_ID]

    # --- PESAN 1: HEADER ---
    title = "Hapus Jadwal" if delete_mode else ("Edit Jadwal" if is_edit_list else "Jadwal Kuliah")
    header_text = f"{title}: <b>{hari_indo(hari)}</b>"

    if is_edit_list:
        prefix = "delete_nav" if delete_mode else "edit_nav"
        back = InlineKeyboardButton("Sebelumnya", callback_data=f"{prefix}:{offset-1}")
        home = InlineKeyboardButton("Hari ini", callback_data=f"{prefix}:0")
        fwd  = InlineKeyboardButton("Berikutnya", callback_data=f"{prefix}:{offset+1}")
        nav_kb = InlineKeyboardMarkup([[back, home, fwd]])
    else:
        nav_kb = nav_jadwal_kb(offset)

    jadwal_ids = []
    jadwal_labels = []

    if not rows:
        list_text = "<i>(Tidak ada jadwal di hari ini)</i>"
    else:
        lines = []

        def format_row(r, idx):
            mk, dosen = _jadwal_info(r['mata_kuliah'], r['dosen'])
            lines = [
                f"{idx}. <code>{r['jam_mulai']}-{r['jam_selesai']}</code>",
                esc(mk),
            ]
            if dosen:
                lines.append(esc(dosen))
            if r["ruangan"]:
                lines.append(f"Ruang: {esc(r['ruangan'])}")
            return "\n".join(lines)

        if jadwal_a:
            lines.append(f"<b>{nama_user(USER_A_ID)}</b>")
            for idx, r in enumerate(jadwal_a, start=1):
                lines.append(format_row(r, idx))
                jadwal_ids.append(r['id'])
                jadwal_labels.append(_jadwal_info(r['mata_kuliah'], r['dosen'])[0])

            if jadwal_b:
                lines.append("")

        if jadwal_b:
            lines.append(f"<b>{nama_user(USER_B_ID)}</b>")
            for idx, r in enumerate(jadwal_b, start=1):
                lines.append(format_row(r, idx))
                jadwal_ids.append(r['id'])
                jadwal_labels.append(_jadwal_info(r['mata_kuliah'], r['dosen'])[0])

        list_text = "\n".join(lines).strip()

    kb_rows = []
    if is_edit_list:
        row = [
            InlineKeyboardButton(
                f"{'Hapus' if delete_mode else 'Edit'} {label[:20]}{'...' if len(label) > 20 else ''}",
                callback_data=f"{'del_jadwal' if delete_mode else 'edit_jadwal'}:{jid}",
            )
            for jid, label in zip(jadwal_ids, jadwal_labels)
        ]
        if row: kb_rows.append(row)

    kb_rows.extend(nav_kb.inline_keyboard)
    final_kb = InlineKeyboardMarkup(kb_rows)
    text = f"{header_text}\n\n{list_text}"

    if edit_mode and update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=final_kb
        )
    elif update.message:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=final_kb
        )

async def show_detail_jadwal(update: Update, context: ContextTypes.DEFAULT_TYPE, jadwal_id: int):
    with db() as conn:
        r = conn.execute("SELECT * FROM jadwal WHERE id=?", (jadwal_id,)).fetchone()

    if not r or not r['aktif']:
        if update.callback_query:
            await update.callback_query.edit_message_text("Jadwal tidak ditemukan atau sudah dihapus.")
        return

    mata_kuliah, dosen = _jadwal_info(r["mata_kuliah"], r["dosen"])
    dosen_text = f"\nDosen: <b>{esc(dosen)}</b>" if dosen else ""
    ruang_text = f"\nRuangan: <b>{esc(r['ruangan'])}</b>" if r["ruangan"] else "\nRuangan: <i>Belum diisi</i>"
    text = (
        f"<b>Detail Jadwal</b>\n\n"
        f"Mata Kuliah: <b>{esc(mata_kuliah)}</b>"
        f"{dosen_text}\n"
        f"Hari: {HARI[r['hari']]}\n"
        f"Waktu: <code>{r['jam_mulai']}-{r['jam_selesai']}</code>\n"
        f"Pemilik: {nama_user(r['user_id'])}"
        f"{ruang_text}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Hapus jadwal", callback_data=f"del_jadwal:{jadwal_id}")]
    ])
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)