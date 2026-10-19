from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import HARI, nama_user, USER_A_ID, USER_B_ID, now_wib
from database import db
from helpers import hari_indo, esc
from keyboards import nav_jadwal_kb, detail_jadwal_kb, aksi_jadwal_kb

async def show_hari_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _render_jadwal(update, context, offset=0, edit_mode=False)

async def _render_jadwal(update, context, offset: int, edit_mode: bool):
    hari = (now_wib().weekday() + offset) % 7

    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM jadwal WHERE hari=? AND aktif=1 ORDER BY jam_mulai",
            (hari,)
        ).fetchall()

    jadwal_a = [r for r in rows if r["user_id"] == USER_A_ID]
    jadwal_b = [r for r in rows if r["user_id"] == USER_B_ID]

    # --- PESAN 1: HEADER + NAVIGASI ---
    header_text = f"📅 <b>Jadwal Kuliah: {hari_indo(hari)}</b>"
    nav_kb = nav_jadwal_kb(offset)

    if edit_mode and update.callback_query:
        await update.callback_query.edit_message_text(header_text, parse_mode="HTML", reply_markup=nav_kb)
    elif update.message:
        await update.message.reply_text(header_text, parse_mode="HTML", reply_markup=nav_kb)

    # --- PESAN 2: DAFTAR KELAS ---
    if not rows:
        if edit_mode:
            await context.bot.send_message(update.effective_chat.id, "<i>(Tidak ada jadwal di hari ini)</i>", parse_mode="HTML")
        elif update.message:
            await update.message.reply_text("<i>(Tidak ada jadwal di hari ini)</i>", parse_mode="HTML")
        return

    lines = []
    jadwal_ids = []
    
    # Kelompokkan berdasarkan user
    lines.append(f"🟦 <b>{nama_user(USER_A_ID)}</b>")
    if jadwal_a:
        for r in jadwal_a:
            idx = len(jadwal_ids) + 1
            ruang = f" • {esc(r['ruangan'])}" if r["ruangan"] else ""
            lines.append(f"{idx}. {r['jam_mulai']}–{r['jam_selesai']} {esc(r['mata_kuliah'])}{ruang}")
            jadwal_ids.append(r['id'])
    else:
        lines.append("  <i>(kosong)</i>")

    lines.append(f"\n🟪 <b>{nama_user(USER_B_ID)}</b>")
    if jadwal_b:
        for r in jadwal_b:
            idx = len(jadwal_ids) + 1
            ruang = f" • {esc(r['ruangan'])}" if r["ruangan"] else ""
            lines.append(f"{idx}. {r['jam_mulai']}–{r['jam_selesai']} {esc(r['mata_kuliah'])}{ruang}")
            jadwal_ids.append(r['id'])
    else:
        lines.append("  <i>(kosong)</i>")

    list_text = "\n".join(lines)
    
    # Gabung tombol Detail (1,2,3) dengan Navigasi (◀️, Hari Ini, ▶️)
    kb_rows = []
    detail_kb = detail_jadwal_kb(jadwal_ids)
    if detail_kb:
        kb_rows.extend(detail_kb.inline_keyboard)
    kb_rows.extend(nav_kb.inline_keyboard)

    final_kb = InlineKeyboardMarkup(kb_rows)

    if edit_mode:
        await context.bot.send_message(update.effective_chat.id, list_text, parse_mode="HTML", reply_markup=final_kb)
    elif update.message:
        await update.message.reply_text(list_text, parse_mode="HTML", reply_markup=final_kb)

async def show_detail_jadwal(update: Update, context: ContextTypes.DEFAULT_TYPE, jadwal_id: int):
    with db() as conn:
        r = conn.execute("SELECT * FROM jadwal WHERE id=?", (jadwal_id,)).fetchone()
    
    if not r or not r['aktif']:
        if update.callback_query:
            await update.callback_query.edit_message_text("Jadwal tidak ditemukan atau sudah dihapus.")
        return

    ruang = f"\n📍 Ruangan: {esc(r['ruangan'])}" if r["ruangan"] else ""
    text = (
        f"📚 <b>Detail Jadwal</b>\n\n"
        f"Mata Kuliah: <b>{esc(r['mata_kuliah'])}</b>\n"
        f"Hari: {HARI[r['hari']]}\n"
        f"Waktu: {r['jam_mulai']}–{r['jam_selesai']}\n"
        f"Pemilik: {nama_user(r['user_id'])}"
        f"{ruang}"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=aksi_jadwal_kb(jadwal_id))