from datetime import timedelta
from telegram import Update
from telegram.ext import ContextTypes
from config import nama_user, USER_A_ID, USER_B_ID, now_wib, BULAN
from database import db
from helpers import rupiah, esc
from keyboards import aksi_pen_kb, nav_keuangan_kb

HARI_NAMA = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

async def show_keuangan(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int = 0, edit_mode: bool = False):
    chat_id = update.effective_chat.id
    current_msg_id = (
        update.callback_query.message.message_id
        if update.callback_query and update.callback_query.message
        else None
    )

    # 1. Bersihkan pesan lama (biar chat nggak numpuk)
    if context.user_data is not None:
        old_msgs = context.user_data.get('keuangan_msgs', [])
        for msg_id in old_msgs:
            if edit_mode and msg_id == current_msg_id:
                continue
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
        context.user_data['keuangan_msgs'] = []

    # 2. Hitung rentang minggu (Senin s.d Minggu)
    today = now_wib()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(weeks=offset)
    end_of_week = start_of_week + timedelta(days=6)

    start_str = start_of_week.strftime("%Y-%m-%d")
    end_str = end_of_week.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    with db() as conn:
        # Ringkasan Total Mingguan
        ringkas = conn.execute("""
            SELECT dibayar_oleh, SUM(nominal) as total, COUNT(*) as jumlah
            FROM pengeluaran
            WHERE dihapus=0 AND tanggal BETWEEN ? AND ?
            GROUP BY dibayar_oleh
        """, (start_str, end_str)).fetchall()

        if offset == 0:
            # Transaksi HARI INI
            transaksi = conn.execute("""
                SELECT * FROM pengeluaran 
                WHERE dihapus=0 AND tanggal = ?
                ORDER BY id ASC
            """, (today_str,)).fetchall()
        else:
            # Jika melihat minggu lain, ambil transaksi minggu tersebut
            transaksi = conn.execute("""
                SELECT * FROM pengeluaran 
                WHERE dihapus=0 AND tanggal BETWEEN ? AND ?
                ORDER BY tanggal ASC, id ASC
            """, (start_str, end_str)).fetchall()

    total_a = total_b = jml_a = jml_b = 0
    for r in ringkas:
        if r["dibayar_oleh"] == USER_A_ID:
            total_a, jml_a = r["total"], r["jumlah"]
        elif r["dibayar_oleh"] == USER_B_ID:
            total_b, jml_b = r["total"], r["jumlah"]
    total_minggu = total_a + total_b

    # Format judul rentang minggu
    tgl_mulai = f"{start_of_week.day} {BULAN[start_of_week.month-1]}"
    tgl_akhir = f"{end_of_week.day} {BULAN[end_of_week.month-1]} {end_of_week.year}"

    lines = [
        f"💰 <b>Keuangan ({tgl_mulai} - {tgl_akhir})</b>",
        f"Total Minggu Ini: <b>{rupiah(total_minggu)}</b>",
        "",
        "━━━━━━━━━━━━━━━━",
    ]

    if offset == 0:
        day_name = HARI_NAMA[today.weekday()]
        total_hari_ini = sum(r["nominal"] for r in transaksi)
        lines.append(f"📅 <b>Transaksi Hari Ini ({day_name}, {today.day} {BULAN[today.month-1]})</b>")
        lines.append(f"Total Hari Ini: <b>{rupiah(total_hari_ini)}</b>")
        if not transaksi:
            lines.append("<i>(Belum ada transaksi hari ini)</i>")
    else:
        if not transaksi:
            lines.append("<i>(Tidak ada transaksi di minggu ini)</i>")
        else:
            lines.append("<b>Transaksi Minggu Ini:</b>")

    summary_text = "\n".join(lines)

    # Kirim / Edit pesan Ringkasan
    if edit_mode and update.callback_query:
        await update.callback_query.edit_message_text(
            summary_text, parse_mode="HTML", reply_markup=nav_keuangan_kb(offset)
        )
        if current_msg_id and context.user_data is not None:
            context.user_data['keuangan_msgs'].append(current_msg_id)
    elif update.message:
        msg = await update.message.reply_text(
            summary_text, parse_mode="HTML", reply_markup=nav_keuangan_kb(offset)
        )
        if context.user_data is not None:
            context.user_data['keuangan_msgs'].append(msg.message_id)

    # Kirim Detail Transaksi hari ini
    for r in transaksi:
        tgl_info = "" if offset == 0 else f" • {r['tanggal']}"
        t_text = (
            f"<b>{esc(r['keterangan'])}</b>\n"
            f"{rupiah(r['nominal'])} • oleh {nama_user(r['dibayar_oleh'])}{tgl_info}"
        )
        m = await context.bot.send_message(
            chat_id, t_text, parse_mode="HTML", reply_markup=aksi_pen_kb(r["id"])
        )
        if context.user_data is not None:
            context.user_data['keuangan_msgs'].append(m.message_id)