from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from config import HARI, nama_user
from database import db
from helpers import valid_jam, valid_nominal, rupiah, esc
from keyboards import pilih_hari_kb, pilih_bayar_kb, menu_utama, aksi_jadwal_kb, aksi_pen_kb
from states import set_state, clear_state

# Buat keyboard batal sekali saja
KB_BATAL = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Batal", callback_data="cancel")]])

async def start_add_jadwal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    set_state(uid, "jf", {"step": "hari"})
    await q.answer()
    await q.edit_message_text(
        "Pilih hari kuliah:",
        reply_markup=pilih_hari_kb("jf:hari")
    )

async def start_add_pen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    set_state(uid, "pf", {"step": "nominal"})
    await q.answer()
    await q.edit_message_text(
        "Ketik nominal pengeluaran:\n(contoh: <code>25000</code> atau <code>25.000</code>)",
        parse_mode="HTML",
        reply_markup=KB_BATAL
    )

async def _handle_jadwal_form(update, uid, ctx, text):
    step = ctx["step"]

    if step == "jam_mulai":
        jam = valid_jam(text)
        if not jam:
            await update.message.reply_text(
                "❌ Format jam salah.\nKetik seperti <code>08:00</code> atau <code>08.00</code>",
                parse_mode="HTML", reply_markup=KB_BATAL
            )
            return
        ctx["jam_mulai"] = jam
        ctx["step"] = "jam_selesai"
        set_state(uid, "jf", ctx)
        await update.message.reply_text(
            "Jam selesai? (contoh: <code>09:40</code>)", 
            parse_mode="HTML", reply_markup=KB_BATAL
        )

    elif step == "jam_selesai":
        jam = valid_jam(text)
        if not jam:
            await update.message.reply_text(
                "❌ Format jam salah.\nKetik seperti <code>09:40</code>", 
                parse_mode="HTML", reply_markup=KB_BATAL
            )
            return
        ctx["jam_selesai"] = jam
        ctx["step"] = "mk"
        set_state(uid, "jf", ctx)
        await update.message.reply_text("Mata kuliah apa?", reply_markup=KB_BATAL)

    elif step == "mk":
        if not text:
            return
        ctx["mata_kuliah"] = text
        ctx["step"] = "ruangan"
        set_state(uid, "jf", ctx)
        await update.message.reply_text(
            "Ruangan? (ketik <code>/skip</code> kalau tidak ada)", 
            parse_mode="HTML", reply_markup=KB_BATAL
        )

    elif step == "ruangan":
        ruangan = None if text.lower() in ("/skip", "skip", "-") else text
        hari = ctx["hari"]
        with db() as conn:
            conn.execute("""
                INSERT INTO jadwal (user_id, hari, jam_mulai, jam_selesai, mata_kuliah, ruangan)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (uid, hari, ctx["jam_mulai"], ctx["jam_selesai"], ctx["mata_kuliah"], ruangan))
        clear_state(uid)
        await update.message.reply_text(
            f"✅ Jadwal <b>{esc(ctx['mata_kuliah'])}</b> tersimpan!\n"
            f"{HARI[hari]} {ctx['jam_mulai']}–{ctx['jam_selesai']}"
            + (f" di {esc(ruangan)}" if ruangan else ""),
            parse_mode="HTML",
            reply_markup=menu_utama()
        )

async def _handle_pen_form(update, uid, ctx, text):
    step = ctx["step"]

    if step == "nominal":
        n = valid_nominal(text)
        if not n:
            await update.message.reply_text(
                "❌ Nominal tidak valid.\nKetik angka saja, contoh: <code>45000</code>", 
                parse_mode="HTML", reply_markup=KB_BATAL
            )
            return
        ctx["nominal"] = n
        ctx["step"] = "keterangan"
        set_state(uid, "pf", ctx)
        await update.message.reply_text(
            "Keterangan pengeluaran? (contoh: <i>makan siang</i>)", 
            parse_mode="HTML", reply_markup=KB_BATAL
        )

    elif step == "keterangan":
        if not text:
            return
        ctx["keterangan"] = text
        ctx["step"] = "bayar"
        set_state(uid, "pf", ctx)
        await update.message.reply_text(
            f"Nominal: <b>{rupiah(ctx['nominal'])}</b>\nKeterangan: {esc(text)}\n\nSiapa yang bayar?",
            parse_mode="HTML",
            reply_markup=pilih_bayar_kb()
        )

async def handle_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, state: str, ctx: dict):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if ctx is None:
        ctx = {}

    if state == "jf":
        await _handle_jadwal_form(update, uid, ctx, text)
    elif state == "pf":
        await _handle_pen_form(update, uid, ctx, text)
    elif state == "ej_wait":
        jid = ctx.get("jadwal_id")
        field = ctx.get("field")
        col_map = {
            "jam_mulai": "jam_mulai",
            "jam_selesai": "jam_selesai",
            "mk": "mata_kuliah",
            "ruangan": "ruangan"
        }
        col = col_map.get(str(field))
        if not col or not jid:
            clear_state(uid)
            await update.message.reply_text("Terjadi kesalahan. Silakan ulangi.", reply_markup=menu_utama())
            return

        val = text
        if field in ("jam_mulai", "jam_selesai"):
            val = valid_jam(text)
            if not val:
                await update.message.reply_text(
                    "❌ Format jam salah. Contoh: <code>08:00</code>",
                    parse_mode="HTML",
                    reply_markup=KB_BATAL
                )
                return
        elif field == "ruangan":
            val = None if text.lower() in ("/skip", "skip", "-") else text

        with db() as conn:
            conn.execute(f"UPDATE jadwal SET {col}=? WHERE id=?", (val, jid))
            row = conn.execute("SELECT * FROM jadwal WHERE id=?", (jid,)).fetchone()

        clear_state(uid)
        if row:
            ruang_str = f"\n📍 {esc(row['ruangan'])}" if row["ruangan"] else ""
            await update.message.reply_text(
                f"✅ Jadwal diperbarui\n\n"
                f"<b>{esc(row['mata_kuliah'])}</b>\n"
                f"{HARI[row['hari']]} {row['jam_mulai']}–{row['jam_selesai']}{ruang_str}",
                parse_mode="HTML",
                reply_markup=aksi_jadwal_kb(jid)
            )
        else:
            await update.message.reply_text("✅ Jadwal diperbarui.", reply_markup=menu_utama())

    elif state == "ep_wait":
        pid = ctx.get("pen_id")
        field = ctx.get("field")
        col_map = {
            "nominal": "nominal",
            "keterangan": "keterangan"
        }
        col = col_map.get(str(field))
        if not col or not pid:
            clear_state(uid)
            await update.message.reply_text("Terjadi kesalahan. Silakan ulangi.", reply_markup=menu_utama())
            return

        val = text
        if field == "nominal":
            val = valid_nominal(text)
            if not val:
                await update.message.reply_text(
                    "❌ Nominal tidak valid. Contoh: <code>25000</code>",
                    parse_mode="HTML",
                    reply_markup=KB_BATAL
                )
                return

        with db() as conn:
            conn.execute(f"UPDATE pengeluaran SET {col}=? WHERE id=?", (val, pid))
            row = conn.execute("SELECT * FROM pengeluaran WHERE id=?", (pid,)).fetchone()

        clear_state(uid)
        if row:
            await update.message.reply_text(
                f"✅ Pengeluaran diperbarui\n\n"
                f"<b>{esc(row['keterangan'])}</b>\n"
                f"{rupiah(row['nominal'])} • oleh {nama_user(row['dibayar_oleh'])} • {row['tanggal']}",
                parse_mode="HTML",
                reply_markup=aksi_pen_kb(pid)
            )
        else:
            await update.message.reply_text("✅ Pengeluaran diperbarui.", reply_markup=menu_utama())

    elif state in ("ej_hari_wait", "ep_bayar_wait"):
        await update.message.reply_text(
            "Silakan pilih opsi pada tombol pesan sebelumnya, atau kirim /cancel untuk batal.",
            reply_markup=KB_BATAL
        )