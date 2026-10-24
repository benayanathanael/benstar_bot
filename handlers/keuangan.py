import datetime
from calendar import monthrange
from datetime import timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from config import nama_user, USER_A_ID, USER_B_ID, now_wib, BULAN
from database import db
from helpers import rupiah, esc
from keyboards import nav_keuangan_kb

HARI_NAMA = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

async def show_keuangan(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    offset: int = 0,
    edit_mode: bool = False,
    owner_override: int | None = None,
    period: str = "minggu_ini",
):
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

    # 2. Hitung rentang transaksi sesuai periode.
    today = now_wib()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(weeks=offset)
    end_of_week = start_of_week + timedelta(days=6)
    if period not in ("hari_ini", "minggu_ini", "bulan_ini", "semua"):
        period = "minggu_ini"
    start_date = start_of_week.date()
    end_date = end_of_week.date()
    if period == "hari_ini":
        start_date = end_date = today.date()
    elif period == "bulan_ini":
        start_date = today.date().replace(day=1)
        end_date = today.date().replace(
            day=monthrange(today.year, today.month)[1]
        )

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    date_filter = "" if period == "semua" else " AND tanggal BETWEEN ? AND ?"
    date_params = [] if period == "semua" else [start_str, end_str]

    with db() as conn:
        ringkas = conn.execute(f"""
            SELECT dibayar_oleh, SUM(nominal) as total, COUNT(*) as jumlah
            FROM pengeluaran
            WHERE dihapus=0{date_filter}
            AND (? IS NULL OR dibayar_oleh=?)
            GROUP BY dibayar_oleh
        """, (*date_params, owner_override, owner_override)).fetchall()

        if period == "minggu_ini" and offset == 0:
            # Transaksi HARI INI
            transaksi = conn.execute("""
                SELECT * FROM pengeluaran 
                WHERE dihapus=0 AND tanggal = ?
                AND (? IS NULL OR dibayar_oleh=?)
                ORDER BY id ASC
            """, (today_str, owner_override, owner_override)).fetchall()
        else:
            transaksi = conn.execute(f"""
                SELECT * FROM pengeluaran 
                WHERE dihapus=0{date_filter}
                AND (? IS NULL OR dibayar_oleh=?)
                ORDER BY tanggal ASC, id ASC
            """, (*date_params, owner_override, owner_override)).fetchall()

    total_a = total_b = jml_a = jml_b = 0
    for r in ringkas:
        if r["dibayar_oleh"] == USER_A_ID:
            total_a, jml_a = r["total"], r["jumlah"]
        elif r["dibayar_oleh"] == USER_B_ID:
            total_b, jml_b = r["total"], r["jumlah"]
    total_periode = total_a + total_b

    tgl_mulai = f"{start_date.day} {BULAN[start_date.month-1]}"
    tgl_akhir = f"{end_date.day} {BULAN[end_date.month-1]} {end_date.year}"
    period_labels = {
        "hari_ini": "hari ini",
        "minggu_ini": "minggu",
        "bulan_ini": "bulan ini",
        "semua": "keseluruhan",
    }
    range_label = (
        "Semua tanggal"
        if period == "semua"
        else f"{tgl_mulai}" if period == "hari_ini"
        else f"{tgl_mulai} - {tgl_akhir}"
    )

    lines = [
        f"<b>Keuangan"
        f"{f' {nama_user(owner_override)}' if owner_override is not None else ''}</b>\n"
        f"{range_label}",
        f"Total {period_labels[period]}: <b>{rupiah(total_periode)}</b>",
        "",
    ]

    if period == "minggu_ini" and offset == 0:
        day_name = HARI_NAMA[today.weekday()]
        total_hari_ini = sum(r["nominal"] for r in transaksi)
        lines.append(f"<b>Transaksi hari ini</b>\n{day_name}, {today.day} {BULAN[today.month-1]}")
        lines.append(f"Total hari ini: <b>{rupiah(total_hari_ini)}</b>")
        if not transaksi:
            lines.append("<i>(Belum ada transaksi hari ini)</i>")
        else:
            lines.append("")
            for index, row in enumerate(transaksi, start=1):
                created_at = row["created_at"] or "-"
                waktu = str(created_at)[11:16] if len(str(created_at)) >= 16 else "-"
                lines.append(
                    f"{index}. {waktu}\n"
                    f"{esc(row['keterangan'])}\n"
                    f"{rupiah(row['nominal'])}\n"
                )
    else:
        if not transaksi:
            lines.append(f"<i>(Tidak ada transaksi untuk {period_labels[period]})</i>")
        else:
            lines.append(f"<b>Transaksi {period_labels[period]}</b>")
            for index, row in enumerate(transaksi[:15], start=1):
                lines.append(
                    f"{index}. {row['tanggal']} - {esc(row['keterangan'])}\n"
                    f"{rupiah(row['nominal'])}"
                )
            if len(transaksi) > 15:
                lines.append(f"...dan {len(transaksi) - 15} transaksi lainnya")

    summary_text = "\n".join(lines)
    reply_markup = nav_keuangan_kb(offset) if period == "minggu_ini" else None

    # Kirim / Edit pesan Ringkasan
    if edit_mode and update.callback_query:
        await update.callback_query.edit_message_text(
            summary_text, parse_mode="HTML", reply_markup=reply_markup
        )
        if current_msg_id and context.user_data is not None:
            context.user_data['keuangan_msgs'].append(current_msg_id)
    elif update.message:
        msg = await update.message.reply_text(
            summary_text, parse_mode="HTML", reply_markup=reply_markup
        )
        if context.user_data is not None:
            context.user_data['keuangan_msgs'].append(msg.message_id)

async def show_edit_keuangan_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    offset: int = 0,
    page: int = 0,
):
    today = now_wib()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_week = start_of_week.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(weeks=offset)
    end_of_week = start_of_week + timedelta(days=6)

    with db() as conn:
        transaksi = conn.execute(
            """
            SELECT * FROM pengeluaran
            WHERE dihapus=0 AND tanggal BETWEEN ? AND ?
            ORDER BY tanggal ASC, id ASC
            """,
            (
                start_of_week.strftime("%Y-%m-%d"),
                end_of_week.strftime("%Y-%m-%d"),
            ),
        ).fetchall()

    tgl_mulai = f"{start_of_week.day} {BULAN[start_of_week.month - 1]}"
    tgl_akhir = f"{end_of_week.day} {BULAN[end_of_week.month - 1]}"
    header = f"<b>Edit Keuangan</b>\n{tgl_mulai} - {tgl_akhir}"

    items_per_page = 5
    total_pages = max(1, (len(transaksi) + items_per_page - 1) // items_per_page)
    page = max(0, min(page, total_pages - 1))
    page_items = transaksi[page * items_per_page:(page + 1) * items_per_page]

    if page_items:
        lines = ["<i>Pilih transaksi yang ingin diedit.</i>", ""]
        for i, row in enumerate(page_items, start=1):
            date = datetime.datetime.strptime(row["tanggal"], "%Y-%m-%d")
            lines.append(
                f"{i}. {date.day}/{date.month} - "
                f"{esc(row['keterangan'])} ({rupiah(row['nominal'])})"
            )
        list_text = "\n".join(lines)
    else:
        list_text = "<i>(Tidak ada transaksi di minggu ini)</i>"

    kb_rows = []
    if page_items:
        kb_rows.append([
            InlineKeyboardButton(
                str(i),
                callback_data=f"edit_pen:{row['id']}",
            )
            for i, row in enumerate(page_items, start=1)
        ])
    if page > 0 or page < total_pages - 1:
        navigation = []
        if page > 0:
            navigation.append(
                InlineKeyboardButton(
                    "Sebelumnya", callback_data=f"edit_k_nav:{offset}:{page - 1}"
                )
            )
        if page < total_pages - 1:
            navigation.append(
                InlineKeyboardButton(
                    "Berikutnya", callback_data=f"edit_k_nav:{offset}:{page + 1}"
                )
            )
        kb_rows.append(navigation)

    text = f"{header}\n\n{list_text}"
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb_rows) if kb_rows else None,
        )
    elif update.message:
        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb_rows) if kb_rows else None,
        )

async def show_delete_keuangan_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    offset: int = 0,
    page: int = 0,
):
    today = now_wib()
    start = (today - timedelta(days=today.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(weeks=offset)
    end = start + timedelta(days=6)

    with db() as conn:
        transaksi = conn.execute(
            """
            SELECT * FROM pengeluaran
            WHERE dihapus=0 AND tanggal BETWEEN ? AND ?
            ORDER BY tanggal ASC, id ASC
            """,
            (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        ).fetchall()

    per_page = 5
    total_pages = max(1, (len(transaksi) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    items = transaksi[page * per_page:(page + 1) * per_page]
    header = (
        f"<b>Hapus Keuangan</b>\n"
        f"{start.day} {BULAN[start.month - 1]} - "
        f"{end.day} {BULAN[end.month - 1]}"
    )

    if items:
        lines = ["<i>Pilih transaksi yang ingin dihapus.</i>", ""]
        for i, row in enumerate(items, start=1):
            date = datetime.datetime.strptime(row["tanggal"], "%Y-%m-%d")
            lines.append(
                f"{i}. {date.day}/{date.month} - "
                f"{esc(row['keterangan'])} ({rupiah(row['nominal'])})"
            )
        text = f"{header}\n\n" + "\n".join(lines)
    else:
        text = f"{header}\n\n<i>(Tidak ada transaksi di minggu ini)</i>"

    rows = []
    if items:
        rows.append([
            InlineKeyboardButton(
                f"Hapus {i}",
                callback_data=f"del_pen:{row['id']}",
            )
            for i, row in enumerate(items, start=1)
        ])
    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                "Sebelumnya",
                callback_data=f"delete_k_nav:{offset}:{page - 1}",
            )
        )
    if page < total_pages - 1:
        navigation.append(
            InlineKeyboardButton(
                "Berikutnya",
                callback_data=f"delete_k_nav:{offset}:{page + 1}",
            )
        )
    if navigation:
        rows.append(navigation)

    markup = InlineKeyboardMarkup(rows) if rows else None
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=markup
        )
    elif update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)