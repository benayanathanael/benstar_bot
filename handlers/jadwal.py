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

async def show_hari_ini(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    owner_id: int | None = None,
):
    await _render_jadwal(
        update,
        context,
        offset=0,
        edit_mode=False,
        is_edit_list=False,
        owner_override=owner_id,
    )

async def show_hari(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    hari: int,
    owner_id: int | None = None,
):
    await _render_jadwal(
        update,
        context,
        offset=0,
        edit_mode=False,
        is_edit_list=False,
        hari_override=hari,
        owner_override=owner_id,
    )

async def show_semua_jadwal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    owner_id: int | None = None,
):
    with db() as conn:
        query = "SELECT * FROM jadwal WHERE aktif=1"
        params = []
        if owner_id is not None:
            query += " AND user_id=?"
            params.append(owner_id)
        query += " ORDER BY hari, jam_mulai"
        rows = conn.execute(query, params).fetchall()

    if not rows:
        pemilik = f" {nama_user(owner_id)}" if owner_id is not None else ""
        await update.message.reply_text(
            f"Belum ada jadwal{pemilik} dari Senin sampai Minggu."
        )
        return

    lines = [
        f"<b>Semua Jadwal{f' {nama_user(owner_id)}' if owner_id is not None else ''}</b>",
        "",
    ]
    for hari in range(7):
        day_rows = [row for row in rows if row["hari"] == hari]
        if not day_rows:
            continue
        lines.append(f"<b>{HARI[hari]}</b>")
        for index, row in enumerate(day_rows, start=1):
            matkul, dosen = _jadwal_info(row["mata_kuliah"], row["dosen"])
            lines.extend([
                f"{index}. <code>{row['jam_mulai']}-{row['jam_selesai']}</code>",
                f"Matkul : {esc(matkul)}",
                f"Dosen : {esc(dosen) if dosen else '-'}",
                f"Ruangan : {esc(row['ruangan']) if row['ruangan'] else '-'}",
                "",
            ])

    await update.message.reply_text("\n".join(lines).strip(), parse_mode="HTML")

async def show_edit_jadwal_list(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0):
    await _render_jadwal(
        update,
        context,
        offset=offset,
        edit_mode=bool(update.callback_query),
        is_edit_list=True,
    )

async def show_edit_jadwal_day(update: Update, context: ContextTypes.DEFAULT_TYPE, hari: int):
    await _render_jadwal(
        update,
        context,
        offset=0,
        edit_mode=False,
        is_edit_list=True,
        hari_override=hari,
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

async def show_delete_jadwal_day(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    hari: int,
    owner_id: int | None = None,
):
    await _render_jadwal(
        update,
        context,
        offset=0,
        edit_mode=False,
        is_edit_list=True,
        delete_mode=True,
        hari_override=hari,
        owner_override=owner_id,
    )

async def _render_jadwal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    offset: int,
    edit_mode: bool,
    is_edit_list: bool,
    delete_mode: bool = False,
    hari_override: int | None = None,
    owner_override: int | None = None,
):
    hari = hari_override if hari_override is not None else (now_wib().weekday() + offset) % 7

    with db() as conn:
        query = "SELECT * FROM jadwal WHERE hari=? AND aktif=1"
        params = [hari]
        if owner_override is not None:
            query += " AND user_id=?"
            params.append(owner_override)
        query += " ORDER BY jam_mulai"
        rows = conn.execute(query, params).fetchall()

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
                f"Matkul : {esc(mk)}",
                f"Dosen : {esc(dosen) if dosen else '-'}",
                f"Ruangan : {esc(r['ruangan']) if r['ruangan'] else '-'}",
            ]
            return "\n".join(lines)

        if jadwal_a:
            lines.append(f"<b>{nama_user(USER_A_ID)}</b>")
            for idx, r in enumerate(jadwal_a, start=1):
                lines.append(format_row(r, idx))
                lines.append("")
                jadwal_ids.append(r['id'])
                jadwal_labels.append(_jadwal_info(r['mata_kuliah'], r['dosen'])[0])

            if jadwal_b:
                lines.append("")

        if jadwal_b:
            lines.append(f"<b>{nama_user(USER_B_ID)}</b>")
            for idx, r in enumerate(jadwal_b, start=1):
                lines.append(format_row(r, idx))
                lines.append("")
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