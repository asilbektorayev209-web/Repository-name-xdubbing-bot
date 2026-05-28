cat > /tmp/bot_v3.py << 'PYEOF'
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
)

# ═══════════════════════════════════════════════════
#                    SOZLAMALAR
# ═══════════════════════════════════════════════════
BOT_TOKEN    = "8485655940:AAE0iMKVKYz8x3iITIR4zhxZv9mmuXvaz9A"
OWNER_ID     = 6857570089
CHANNEL_ID   = -1003897588293
MAIN_CHANNEL = "@FxDubbing"
CHECK_INTERVAL = 6 * 3600

MONTH_LABEL = {
    "1": "1 Oylik — 25,000 so'm", "3": "3 Oylik — 50,000 so'm",
    "6": "6 Oylik — 100,000 so'm", "12": "1 Yillik — 250,000 so'm",
}
MONTH_DELTA = {"1": 1, "3": 3, "6": 6, "12": 12}

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

USER_KB = ReplyKeyboardMarkup([
    ["💎 Premium Kanal", "📞 Biz Bilan Bog'lanish"],
    ["📖 Bot Qo'llanmasi"],
], resize_keyboard=True)

ADMIN_KB = ReplyKeyboardMarkup([["🔧 Admin Panel"]], resize_keyboard=True)


# ═══════════════════════════════════════════════════
#                    DATABASE
# ═══════════════════════════════════════════════════
def init_db():
    with sqlite3.connect("bot.db") as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
            joined_at TEXT, state TEXT DEFAULT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY, added_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, months INTEGER,
            start_date TEXT, end_date TEXT,
            warned_7 INTEGER DEFAULT 0, warned_3 INTEGER DEFAULT 0,
            warned_1 INTEGER DEFAULT 0, active INTEGER DEFAULT 1)""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS tutorials (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, file_id TEXT, added_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS saved_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, channel_id TEXT)""")
        c.execute("INSERT OR IGNORE INTO admins (admin_id, added_at) VALUES (?,?)",
                  (OWNER_ID, datetime.now().isoformat()))
        for k, v in [("support_phone", "+998 xx xxx xx xx"),
                     ("support_username", "@support_username"),
                     ("card_number", "5614 6816 2654 6851"),
                     ("card_owner", "N. F")]:
            c.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (k, v))
        conn.commit()

def gs(key, default=""):
    with sqlite3.connect("bot.db") as conn:
        r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default

def ss(key, value):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value))

def db_add_user(uid, username, full_name):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id,username,full_name,joined_at) VALUES (?,?,?,?)",
                     (uid, username or "", full_name or "", datetime.now().isoformat()))

def db_set_state(uid, state):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("UPDATE users SET state=? WHERE user_id=?", (state, uid))

def db_get_state(uid):
    with sqlite3.connect("bot.db") as conn:
        r = conn.execute("SELECT state FROM users WHERE user_id=?", (uid,)).fetchone()
    return r[0] if r else None

def db_user_ids():
    with sqlite3.connect("bot.db") as conn:
        return [r[0] for r in conn.execute("SELECT user_id FROM users").fetchall()]

def db_user_count():
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

def db_today_count():
    today = datetime.now().date().isoformat()
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{today}%",)).fetchone()[0]

def db_get_admins():
    with sqlite3.connect("bot.db") as conn:
        return [r[0] for r in conn.execute("SELECT admin_id FROM admins").fetchall()]

def db_add_admin(aid):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT OR IGNORE INTO admins (admin_id,added_at) VALUES (?,?)",
                     (aid, datetime.now().isoformat()))

def db_rem_admin(aid):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("DELETE FROM admins WHERE admin_id=?", (aid,))

def is_admin(uid): return uid == OWNER_ID or uid in db_get_admins()

def db_add_sub(uid, months):
    start = datetime.now()
    end   = start + timedelta(days=30 * months)
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT INTO subscriptions (user_id,months,start_date,end_date) VALUES (?,?,?,?)",
                     (uid, months, start.isoformat(), end.isoformat()))

def db_active_subs():
    with sqlite3.connect("bot.db") as conn:
        return conn.execute(
            "SELECT id,user_id,months,end_date FROM subscriptions WHERE active=1 ORDER BY end_date"
        ).fetchall()

def db_active_count():
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT COUNT(*) FROM subscriptions WHERE active=1").fetchone()[0]

def db_expired():
    now = datetime.now().isoformat()
    with sqlite3.connect("bot.db") as conn:
        return conn.execute(
            "SELECT id,user_id FROM subscriptions WHERE active=1 AND end_date<=?", (now,)).fetchall()

def db_deactivate(sub_id):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("UPDATE subscriptions SET active=0 WHERE id=?", (sub_id,))

def db_warn_subs(days, col):
    deadline = (datetime.now() + timedelta(days=days)).isoformat()
    now      = datetime.now().isoformat()
    with sqlite3.connect("bot.db") as conn:
        return conn.execute(
            f"SELECT id,user_id,end_date FROM subscriptions "
            f"WHERE active=1 AND {col}=0 AND end_date<=? AND end_date>?", (deadline, now)
        ).fetchall()

def db_mark_warn(sub_id, col):
    with sqlite3.connect("bot.db") as conn:
        conn.execute(f"UPDATE subscriptions SET {col}=1 WHERE id=?", (sub_id,))

def db_tutorials():
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT id,title,file_id FROM tutorials ORDER BY id").fetchall()

def db_add_tutorial(title, fid):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT INTO tutorials (title,file_id,added_at) VALUES (?,?,?)",
                     (title, fid, datetime.now().isoformat()))

def db_del_tutorial(tid):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("DELETE FROM tutorials WHERE id=?", (tid,))

def db_channels():
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT id,name,channel_id FROM saved_channels").fetchall()

def db_add_channel(name, cid):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT INTO saved_channels (name,channel_id) VALUES (?,?)", (name, cid))

def db_del_channel(cid):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("DELETE FROM saved_channels WHERE id=?", (cid,))


# ═══════════════════════════════════════════════════
#              ADMIN PANEL KLAVIATURALAR
# ═══════════════════════════════════════════════════
def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistika",  callback_data="m_stats"),
         InlineKeyboardButton("📝 Post Yozish", callback_data="m_post")],
        [InlineKeyboardButton("💎 Obunalar",    callback_data="m_subs"),
         InlineKeyboardButton("📞 Support",     callback_data="m_support")],
        [InlineKeyboardButton("🎓 Darslik",     callback_data="m_tutorial"),
         InlineKeyboardButton("⚙️ Sozlamalar",  callback_data="m_settings")],
    ])

def kb_stats():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👥 Foydalanuvchilar: {db_user_count()} ta", callback_data="noop"),
         InlineKeyboardButton(f"📅 Bugun: {db_today_count()} ta",           callback_data="noop")],
        [InlineKeyboardButton(f"💎 Faol obunalar: {db_active_count()} ta",  callback_data="noop"),
         InlineKeyboardButton(f"👤 Adminlar: {len(db_get_admins())} ta",    callback_data="noop")],
        [InlineKeyboardButton("📋 Adminlar ro'yxati", callback_data="s_list")],
        [InlineKeyboardButton("➕ Admin qo'shish",    callback_data="s_add"),
         InlineKeyboardButton("➖ Admin o'chirish",   callback_data="s_del")],
        [InlineKeyboardButton("◀️ Ortga", callback_data="m_main")],
    ])

def kb_post():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Rasmli post",  callback_data="pt_photo"),
         InlineKeyboardButton("📝 Matnli post",  callback_data="pt_text")],
        [InlineKeyboardButton("🎤 Ovozli xabar", callback_data="pt_voice"),
         InlineKeyboardButton("🎥 Video xabar",  callback_data="pt_video")],
        [InlineKeyboardButton("◀️ Ortga", callback_data="m_main")],
    ])

def kb_post_btns():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tugmali",      callback_data="pb_yes"),
         InlineKeyboardButton("❌ Tugmasiz",     callback_data="pb_no")],
        [InlineKeyboardButton("◀️ Bekor qilish", callback_data="m_post")],
    ])

def kb_dest():
    rows = [
        [InlineKeyboardButton("💎 Premium kanal",    callback_data="pd_premium"),
         InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="pd_users")],
        [InlineKeyboardButton("📢 Asosiy kanal (@FxDubbing)", callback_data="pd_main")],
        [InlineKeyboardButton("🌐 Hammasiga yuborish", callback_data="pd_all")],
    ]
    for ch in db_channels():
        rows.append([InlineKeyboardButton(f"📡 {ch[1]}", callback_data=f"pd_c{ch[0]}")])
    rows.append([InlineKeyboardButton("◀️ Bekor qilish", callback_data="m_post")])
    return InlineKeyboardMarkup(rows)

def kb_support():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📞 {gs('support_phone')}", callback_data="noop")],
        [InlineKeyboardButton(f"👤 {gs('support_username')}", callback_data="noop")],
        [InlineKeyboardButton("📞 Telefon o'zgartirish",  callback_data="sp_phone"),
         InlineKeyboardButton("👤 Username o'zgartirish", callback_data="sp_user")],
        [InlineKeyboardButton("◀️ Ortga", callback_data="m_main")],
    ])

def kb_tutorial():
    rows = [[InlineKeyboardButton("➕ Darslik qo'shish", callback_data="tu_add")]]
    for t in db_tutorials():
        rows.append([InlineKeyboardButton(f"🎓 {t[1]}", callback_data="noop"),
                     InlineKeyboardButton("🗑", callback_data=f"tu_del_{t[0]}")])
    if not db_tutorials():
        rows.append([InlineKeyboardButton("📭 Hozircha darslik yo'q", callback_data="noop")])
    rows.append([InlineKeyboardButton("◀️ Ortga", callback_data="m_main")])
    return InlineKeyboardMarkup(rows)

def kb_settings():
    rows = [
        [InlineKeyboardButton(f"💳 {gs('card_number')}", callback_data="noop")],
        [InlineKeyboardButton(f"👤 {gs('card_owner')}",  callback_data="noop")],
        [InlineKeyboardButton("💳 Karta o'zgartirish",   callback_data="se_card"),
         InlineKeyboardButton("👤 Egasini o'zgartirish", callback_data="se_owner")],
        [InlineKeyboardButton("📡 Kanal qo'shish",       callback_data="se_addch"),
         InlineKeyboardButton("📡 Kanal o'chirish",      callback_data="se_delch")],
        [InlineKeyboardButton("◀️ Ortga", callback_data="m_main")],
    ]
    return InlineKeyboardMarkup(rows)

def kb_subs():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Faol obunalar ro'yxati", callback_data="su_list")],
        [InlineKeyboardButton("🗑 Qo'lda chiqarish",       callback_data="su_kick")],
        [InlineKeyboardButton("◀️ Ortga",                   callback_data="m_main")],
    ])


# ═══════════════════════════════════════════════════
#                  /START & /ADMIN
# ═══════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_add_user(user.id, user.username, user.full_name)
    db_set_state(user.id, None)
    context.user_data.clear()
    await update.message.reply_text(
        "Assalom Aleykum Xurmatli Foydalanuvchi! 👋\n\n"
        "Siz <b>X-Dubbing Studiyasining</b> Botidasiz!\n"
        "Bizdan qanday xizmat?\n\n"
        "Iltimos pastgi qatordagi tugmalar yordamida men bilan gaplashing!",
        parse_mode="HTML",
        reply_markup=ADMIN_KB if is_admin(user.id) else USER_KB,
    )

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text(
        "🔧 <b>Admin Boshqaruv Paneli</b>\n\nBo'lim tanlang:",
        parse_mode="HTML", reply_markup=kb_main())


# ═══════════════════════════════════════════════════
#          FOYDALANUVCHI TUGMA HANDLERLARI
# ═══════════════════════════════════════════════════
async def user_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 <b>X-DUBBING PREMIUM HAQIDA MALUMOT!</b>\n\n"
        "Bu pullik kanal bo'lib faqat pul to'lab kirishingiz mumkin 💳\n\n"
        "<b>WERX PREMIUM NARXI:</b>\n"
        "💎 1 Oylik = 25 Ming\n💎 3 Oylik = 50 Ming\n"
        "💎 6 Oylik = 100 Ming\n💎 1 Yillik = 250 Ming\n\n"
        "‼️ <i>Chekni Yuborgach Biroz Kuting. Odatda 5-15 Daqiqada Javob olasiz."
        " Ammo Hayot mamot masalalari bilan bo'lib qolgan paytlar 6-12 soatgacha"
        " kutishga to'g'ri kelishi mumkin. Albatta bunaqasi kam bo'ladi</i> ‼️",
        parse_mode="HTML")
    await update.message.reply_text(
        "Pastdagi Havolaga bosing va Qo'shilish so'rovini yuboring!\n"
        "Keyin esa To'lov qilib rasm yuboring! 👇\n\n"
        '🔗 <a href="https://t.me/+bUQj_WkfOAphNzMy">Kanalga O\'tish</a>\n\n'
        f"💳 <b>To'lov Karta Raqami:</b>\n<code>{gs('card_number')}</code>\n"
        f"Shaxs: {gs('card_owner')}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 TO'LOV QILISH", callback_data="pay_now")]]))

async def user_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📞 <b>Biz Bilan Bog'lanish</b>\n\n"
        "Biror Muammo yoki Taklif bo'lsa:\n\n"
        f"📱 {gs('support_phone')}\n💬 {gs('support_username')}\n\n"
        "Aloqaga chiqing!\n"
        "<i>Admin bot kabi 24/7 ishlamaydi. Biroz kutishga to'g'ri kelishi mumkin.</i>",
        parse_mode="HTML")

async def user_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tuts = db_tutorials()
    if not tuts:
        await update.message.reply_text("📭 Hozircha qo'llanma qo'shilmagan. Tez orada!")
        return
    await update.message.reply_text("🎓 <b>Bot Qo'llanmasi:</b>", parse_mode="HTML")
    for t in tuts:
        try:
            await context.bot.send_video(
                chat_id=update.effective_user.id,
                video=t[2], caption=f"📖 <b>{t[1]}</b>", parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Tutorial: {e}")


# ═══════════════════════════════════════════════════
#         CALLBACK — TO'LOV TUGMASI
# ═══════════════════════════════════════════════════
async def cb_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    db_set_state(q.from_user.id, "waiting_pay")
    await q.message.reply_text(
        "💳 <b>To'lov O'tkazmasi</b>\n\n"
        "Pul o'tkazmasi rasmini yuboring!\n\n⏳ Kutyabman....",
        parse_mode="HTML")


# ═══════════════════════════════════════════════════
#         CALLBACK — CHEK TASDIQLASH
# ═══════════════════════════════════════════════════
async def cb_chek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    p      = q.data.split("_")
    action = p[1]
    uid    = int(p[-1])

    if action == "ok":
        ms  = p[2]
        mi  = MONTH_DELTA[ms]
        lbl = MONTH_LABEL[ms]
        end = (datetime.now() + timedelta(days=30 * mi)).strftime("%d.%m.%Y")
        try:
            await context.bot.approve_chat_join_request(chat_id=CHANNEL_ID, user_id=uid)
            db_add_sub(uid, mi)
            await context.bot.send_message(chat_id=uid, parse_mode="HTML",
                text=(f"✅ <b>Tabriklaymiz!</b>\n\n💎 <b>{lbl}</b> obunangiz tasdiqlandi!\n"
                      f"📅 Tugash sanasi: <b>{end}</b>\n\nKanalga muvaffaqiyatli qo'shildingiz! Xush kelibsiz 🎉"))
            await q.edit_message_text(
                f"✅ <b>Tasdiqlandi!</b>\n👤 <code>{uid}</code> → 💎 {lbl}\n📅 {end}",
                parse_mode="HTML")
        except Exception as e:
            err = str(e).lower()
            if "hide_requester_missing" in err or "user_not_participant" in err:
                msg = ("⚠️ <b>Foydalanuvchi hali kanalga qo'shilish so'rovi yubormaganga o'xshaydi.</b>\n\n"
                       "Foydalanuvchiga kanalga o'tib, qo'shilish so'rovi yuborishni ayting, so'ng qayta tasdiqlang.")
            else:
                msg = f"❌ Xato:\n<code>{e}</code>"
            await q.edit_message_text(msg, parse_mode="HTML")

    elif action == "rad":
        try:
            await context.bot.decline_chat_join_request(chat_id=CHANNEL_ID, user_id=uid)
        except Exception: pass
        try:
            await context.bot.send_message(chat_id=uid, parse_mode="HTML",
                text="❌ <b>Chekingiz tasdiqlanmadi.</b>\n\nIltimos, to'g'ri chek yuboring.")
        except Exception: pass
        await q.edit_message_text(f"❌ Rad — <code>{uid}</code>", parse_mode="HTML")


# ═══════════════════════════════════════════════════
#             CALLBACK — ADMIN PANEL
# ═══════════════════════════════════════════════════
async def cb_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id): return
    d = q.data

    if d == "noop": return

    # ── Ana menu ──────────────────────────────────
    if d == "m_main":
        context.user_data.pop("astate", None)
        context.user_data.pop("post", None)
        context.user_data.pop("tut_title", None)
        context.user_data.pop("ch_name", None)
        await q.edit_message_text("🔧 <b>Admin Boshqaruv Paneli</b>\n\nBo'lim tanlang:",
                                  parse_mode="HTML", reply_markup=kb_main())

    elif d == "m_stats":
        await q.edit_message_text("📊 <b>Statistika Bo'limi</b>",
                                  parse_mode="HTML", reply_markup=kb_stats())

    elif d == "m_post":
        context.user_data.clear()
        await q.edit_message_text("📝 <b>Post Yozish</b>\n\nPost turini tanlang:",
                                  parse_mode="HTML", reply_markup=kb_post())

    elif d == "m_subs":
        await q.edit_message_text("💎 <b>Obunalar Bo'limi</b>",
                                  parse_mode="HTML", reply_markup=kb_subs())

    elif d == "m_support":
        await q.edit_message_text("📞 <b>Support Sozlamalari</b>",
                                  parse_mode="HTML", reply_markup=kb_support())

    elif d == "m_tutorial":
        await q.edit_message_text("🎓 <b>Darsliklar Bo'limi</b>",
                                  parse_mode="HTML", reply_markup=kb_tutorial())

    elif d == "m_settings":
        await q.edit_message_text("⚙️ <b>Bot Sozlamalari</b>",
                                  parse_mode="HTML", reply_markup=kb_settings())

    # ── Statistika ────────────────────────────────
    elif d == "s_list":
        admins = db_get_admins()
        lines  = [f"• <code>{a}</code>{'  👑 Egasi' if a == OWNER_ID else ''}" for a in admins]
        await q.edit_message_text("📋 <b>Adminlar ro'yxati:</b>\n\n" + "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Ortga", callback_data="m_stats")]]))

    elif d == "s_add":
        context.user_data["astate"] = "addadmin"
        await q.edit_message_text("➕ Yangi admin <b>Telegram ID</b>sini yuboring:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor", callback_data="m_stats")]]))

    elif d == "s_del":
        context.user_data["astate"] = "deladmin"
        await q.edit_message_text("➖ O'chiriladigan admin <b>ID</b>sini yuboring:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor", callback_data="m_stats")]]))

    # ── Post ──────────────────────────────────────
    elif d.startswith("pt_"):
        ptype = d[3:]
        context.user_data["post"]   = {"type": ptype}
        context.user_data["astate"] = f"post_{ptype}"
        prompts = {"photo": "🖼 Rasm yuboring 👇", "text": "📝 Matn kiriting 👇",
                   "voice": "🎤 Ovozli xabar yuboring 👇", "video": "🎥 Video yuboring 👇"}
        await q.edit_message_text(f"📝 <b>Post yaratish</b>\n\n{prompts.get(ptype, '')}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor", callback_data="m_post")]]))

    elif d == "pb_yes":
        context.user_data["astate"] = "post_buttons"
        await q.edit_message_text(
            "🔘 <b>Tugmalar kiriting:</b>\n\n"
            "Har qatorda: <code>Tugma nomi|https://havola</code>\n\n"
            "📌 Misol:\n<code>▶️ Tomosha qilish|https://t.me/uzdubgo\n"
            "💎 Premium|https://t.me/+bUQj_WkfOAphNzMy\n📱 Ilova|https://t.me/uzdubgo</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor", callback_data="m_post")]]))

    elif d == "pb_no":
        context.user_data.get("post", {})["buttons"] = []
        context.user_data.pop("astate", None)
        await q.edit_message_text("📍 <b>Qayerga yuboramiz?</b>",
                                  parse_mode="HTML", reply_markup=kb_dest())

    elif d.startswith("pd_"):
        await do_send_post(q, context, d)

    # ── Obunalar ──────────────────────────────────
    elif d == "su_list":
        subs = db_active_subs()
        if not subs:
            text = "💎 Hozircha faol obuna yo'q."
        else:
            lines = [f"• <code>{s[1]}</code> — {s[2]} oy — <b>{datetime.fromisoformat(s[3]).strftime('%d.%m.%Y')}</b>"
                     for s in subs]
            text = "💎 <b>Faol obunalar:</b>\n\n" + "\n".join(lines)
        await q.edit_message_text(text, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Ortga", callback_data="m_subs")]]))

    elif d == "su_kick":
        context.user_data["astate"] = "kick"
        await q.edit_message_text("🗑 Chiqariladigan foydalanuvchi <b>Telegram ID</b>sini yuboring:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor", callback_data="m_subs")]]))

    # ── Support ───────────────────────────────────
    elif d == "sp_phone":
        context.user_data["astate"] = "sup_phone"
        await q.edit_message_text("📞 Yangi telefon raqamni yuboring:\n<i>Misol: +998 90 123 45 67</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor", callback_data="m_support")]]))

    elif d == "sp_user":
        context.user_data["astate"] = "sup_user"
        await q.edit_message_text("👤 Yangi username yuboring:\n<i>Misol: @username</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor", callback_data="m_support")]]))

    # ── Darslik ───────────────────────────────────
    elif d == "tu_add":
        context.user_data["astate"] = "tut_title"
        await q.edit_message_text("🎓 Darslik <b>nomini</b> kiriting:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor", callback_data="m_tutorial")]]))

    elif d.startswith("tu_del_"):
        db_del_tutorial(int(d[7:]))
        await q.edit_message_text("🎓 <b>Darsliklar Bo'limi</b>\n\n✅ O'chirildi.",
                                  parse_mode="HTML", reply_markup=kb_tutorial())

    # ── Sozlamalar ────────────────────────────────
    elif d == "se_card":
        context.user_data["astate"] = "set_card"
        await q.edit_message_text("💳 Yangi karta raqamini yuboring:\n<i>Misol: 1234 5678 9012 3456</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor", callback_data="m_settings")]]))

    elif d == "se_owner":
        context.user_data["astate"] = "set_owner"
        await q.edit_message_text("👤 Karta egasining ismini yuboring:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor", callback_data="m_settings")]]))

    elif d == "se_addch":
        context.user_data["astate"] = "ch_name"
        await q.edit_message_text("📡 Yangi kanal <b>nomini</b> kiriting:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Bekor", callback_data="m_settings")]]))

    elif d == "se_delch":
        chs = db_channels()
        if not chs:
            await q.edit_message_text("📡 Saqlangan kanal yo'q.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Ortga", callback_data="m_settings")]]))
        else:
            rows = [[InlineKeyboardButton(f"🗑 {c[1]}", callback_data=f"ch_del_{c[0]}")] for c in chs]
            rows.append([InlineKeyboardButton("◀️ Ortga", callback_data="m_settings")])
            await q.edit_message_text("📡 <b>Qaysi kanalni o'chirish?</b>",
                                      parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))

    elif d.startswith("ch_del_"):
        db_del_channel(int(d[7:]))
        await q.edit_message_text("⚙️ <b>Bot Sozlamalari</b>\n\n✅ Kanal o'chirildi.",
                                  parse_mode="HTML", reply_markup=kb_settings())


# ═══════════════════════════════════════════════════
#              POST YUBORISH HELPER
# ═══════════════════════════════════════════════════
async def do_send_post(q, context, dest):
    post    = context.user_data.get("post", {})
    ptype   = post.get("type")
    content = post.get("content")
    caption = post.get("caption", "")
    buttons = post.get("buttons", [])
    markup  = InlineKeyboardMarkup(buttons) if buttons else None

    if not content:
        await q.edit_message_text("❌ Post ma'lumoti topilmadi.")
        return

    await q.edit_message_text("⏳ Yuborilmoqda...")
    aid = q.from_user.id

    if dest == "pd_premium":     targets = [CHANNEL_ID]
    elif dest == "pd_users":     targets = db_user_ids()
    elif dest == "pd_main":      targets = [MAIN_CHANNEL]
    elif dest == "pd_all":       targets = [CHANNEL_ID, MAIN_CHANNEL] + db_user_ids()
    elif dest.startswith("pd_c"):
        cid = int(dest[4:])
        targets = [c[2] for c in db_channels() if c[0] == cid]
    else:
        targets = []

    ok = fail = 0

    async def send_one(t):
        nonlocal ok, fail
        try:
            if ptype == "photo":
                await context.bot.send_photo(chat_id=t, photo=content,
                    caption=caption or None, reply_markup=markup, parse_mode="HTML")
            elif ptype == "text":
                await context.bot.send_message(chat_id=t, text=content,
                    reply_markup=markup, parse_mode="HTML")
            elif ptype == "voice":
                await context.bot.send_voice(chat_id=t, voice=content,
                    caption=caption or None, reply_markup=markup)
            elif ptype == "video":
                await context.bot.send_video(chat_id=t, video=content,
                    caption=caption or None, reply_markup=markup, parse_mode="HTML")
            ok += 1
        except Exception as e:
            fail += 1
            err = str(e).lower()
            if any(x in err for x in ["not enough rights", "forbidden", "admin", "chat_admin"]):
                try:
                    await context.bot.send_message(chat_id=aid, parse_mode="HTML",
                        text=f"⚠️ <b>Bot bu kanalda admin emas!</b>\n<code>{t}</code>\nBotni admin qiling.")
                except Exception: pass

    for t in targets:
        await send_one(t)

    context.user_data.pop("post", None)
    context.user_data.pop("astate", None)
    await q.edit_message_text(
        f"✅ <b>Post yuborildi!</b>\n\n✅ Muvaffaqiyatli: {ok}\n❌ Xato: {fail}",
        parse_mode="HTML")


# ═══════════════════════════════════════════════════
#           MEDIA HANDLERLAR
# ═══════════════════════════════════════════════════
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    astate = context.user_data.get("astate")

    if is_admin(user.id) and astate == "post_photo":
        context.user_data["post"]["content"] = update.message.photo[-1].file_id
        context.user_data["post"]["caption"] = update.message.caption or ""
        context.user_data.pop("astate", None)
        await update.message.reply_text("✅ Rasm qabul qilindi!\n\nTugma qo'shilsinmi?",
                                        reply_markup=kb_post_btns())
        return

    if db_get_state(user.id) == "waiting_pay":
        db_set_state(user.id, None)
        await update.message.reply_text(
            "⏳ <b>Tasdiqlash Jarayonida...</b>\n\nAdminlar chekingizni tekshirmoqda, biroz kuting!",
            parse_mode="HTML")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 1 Oylik (25K)",  callback_data=f"chk_ok_1_{user.id}"),
             InlineKeyboardButton("💎 3 Oylik (50K)",  callback_data=f"chk_ok_3_{user.id}")],
            [InlineKeyboardButton("💎 6 Oylik (100K)", callback_data=f"chk_ok_6_{user.id}"),
             InlineKeyboardButton("💎 1 Yillik (250K)",callback_data=f"chk_ok_12_{user.id}")],
            [InlineKeyboardButton("❌ Rad Etish",       callback_data=f"chk_rad_0_{user.id}")],
        ])
        uname = f"@{user.username}" if user.username else "Yo'q"
        info  = (f"📸 <b>Yangi Chek Keldi!</b>\n\n👤 Ism: {user.full_name}\n"
                 f"🆔 ID: <code>{user.id}</code>\n📱 Username: {uname}\n\n"
                 f"Chekni tekshirib, mos obuna turini tanlang 👇")
        for aid in db_get_admins():
            try:
                await context.bot.forward_message(
                    chat_id=aid, from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id)
                await context.bot.send_message(
                    chat_id=aid, text=info, parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                logger.warning(f"Forward: {e}")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    astate = context.user_data.get("astate")
    if not is_admin(user.id): return
    fid = update.message.video.file_id if update.message.video else (
          update.message.document.file_id if update.message.document else None)
    if not fid: return

    if astate == "post_video":
        context.user_data["post"]["content"] = fid
        context.user_data["post"]["caption"] = update.message.caption or ""
        context.user_data.pop("astate", None)
        await update.message.reply_text("✅ Video qabul qilindi!\n\nTugma qo'shilsinmi?",
                                        reply_markup=kb_post_btns())

    elif astate == "tut_video":
        title = context.user_data.pop("tut_title", "Darslik")
        db_add_tutorial(title, fid)
        context.user_data.pop("astate", None)
        await update.message.reply_text(f"✅ <b>'{title}'</b> darsligi qo'shildi!", parse_mode="HTML")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user   = update.effective_user
    astate = context.user_data.get("astate")
    if is_admin(user.id) and astate == "post_voice":
        context.user_data["post"]["content"] = update.message.voice.file_id
        context.user_data["post"]["caption"] = ""
        context.user_data.pop("astate", None)
        await update.message.reply_text("✅ Ovozli xabar qabul qilindi!\n\nTugma qo'shilsinmi?",
                                        reply_markup=kb_post_btns())


# ═══════════════════════════════════════════════════
#                MATN HANDLER
# ═══════════════════════════════════════════════════
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()

    if text == "💎 Premium Kanal":          await user_premium(update, context);  return
    if text == "📞 Biz Bilan Bog'lanish":   await user_support(update, context);  return
    if text == "📖 Bot Qo'llanmasi":        await user_tutorial(update, context); return
    if text == "🔧 Admin Panel" and is_admin(uid): await cmd_admin(update, context); return

    if not is_admin(uid): return
    astate = context.user_data.get("astate")

    if astate == "post_text":
        context.user_data["post"]["content"] = text
        context.user_data["post"]["caption"] = ""
        context.user_data.pop("astate", None)
        await update.message.reply_text("✅ Matn qabul qilindi!\n\nTugma qo'shilsinmi?",
                                        reply_markup=kb_post_btns()); return

    if astate == "post_buttons":
        rows = []
        for line in text.splitlines():
            if "|" in line:
                lbl, url = line.split("|", 1)
                rows.append([InlineKeyboardButton(lbl.strip(), url=url.strip())])
        context.user_data["post"]["buttons"] = rows
        context.user_data.pop("astate", None)
        await update.message.reply_text(
            f"✅ <b>{len(rows)} ta tugma</b> qo'shildi!\n\n📍 Qayerga yuboramiz?",
            parse_mode="HTML", reply_markup=kb_dest()); return

    if astate == "addadmin":
        context.user_data.pop("astate", None)
        try:
            db_add_admin(int(text))
            await update.message.reply_text(f"✅ Admin qo'shildi: <code>{text}</code>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Faqat raqam kiriting!")
        return

    if astate == "deladmin":
        context.user_data.pop("astate", None)
        try:
            rid = int(text)
            if rid == OWNER_ID: await update.message.reply_text("❌ Egani o'chirib bo'lmaydi!")
            else:
                db_rem_admin(rid)
                await update.message.reply_text(f"✅ Admin o'chirildi: <code>{rid}</code>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Faqat raqam kiriting!")
        return

    if astate == "sup_phone":
        context.user_data.pop("astate", None)
        ss("support_phone", text)
        await update.message.reply_text(f"✅ Telefon yangilandi: {text}"); return

    if astate == "sup_user":
        context.user_data.pop("astate", None)
        ss("support_username", text)
        await update.message.reply_text(f"✅ Username yangilandi: {text}"); return

    if astate == "set_card":
        context.user_data.pop("astate", None)
        ss("card_number", text)
        await update.message.reply_text(f"✅ Karta yangilandi:\n<code>{text}</code>", parse_mode="HTML"); return

    if astate == "set_owner":
        context.user_data.pop("astate", None)
        ss("card_owner", text)
        await update.message.reply_text(f"✅ Karta egasi: {text}"); return

    if astate == "tut_title":
        context.user_data["tut_title"] = text
        context.user_data["astate"]    = "tut_video"
        await update.message.reply_text(
            f"✅ Nom: <b>{text}</b>\n\nEndi darslik <b>videosini</b> yuboring:",
            parse_mode="HTML"); return

    if astate == "ch_name":
        context.user_data["ch_name"] = text
        context.user_data["astate"]  = "ch_id"
        await update.message.reply_text(
            f"✅ Nom: <b>{text}</b>\n\nKanal <b>ID</b> yoki <b>@username</b>ini yuboring:\n"
            f"<i>Misol: -1001234567890 yoki @mychannnel</i>", parse_mode="HTML"); return

    if astate == "ch_id":
        context.user_data.pop("astate", None)
        name = context.user_data.pop("ch_name", "Kanal")
        db_add_channel(name, text)
        await update.message.reply_text(
            f"✅ Kanal qo'shildi!\n📡 Nom: <b>{name}</b>\n🔗 ID: <code>{text}</code>",
            parse_mode="HTML"); return

    if astate == "kick":
        context.user_data.pop("astate", None)
        try:
            kid = int(text)
            await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=kid)
            await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=kid)
            try:
                await context.bot.send_message(chat_id=kid, parse_mode="HTML",
                    text="⚠️ <b>Obunangiz tugadi yoki bekor qilindi.</b>\n\n"
                         "Kanaldan chiqarildingiz. (Qayta kira olasiz ✅)\n"
                         "Davom etish uchun /start")
            except Exception: pass
            await update.message.reply_text(
                f"✅ <code>{kid}</code> chiqarildi. Blok qo'yilmadi ✅", parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ Xato: <code>{e}</code>", parse_mode="HTML")
        return


# ═══════════════════════════════════════════════════
#            AVTOMATIK OBUNA TEKSHIRUVI
# ═══════════════════════════════════════════════════
async def job_subs(context: ContextTypes.DEFAULT_TYPE):
    for sub_id, uid in db_expired():
        try:
            await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=uid)
            await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=uid)
            await context.bot.send_message(chat_id=uid, parse_mode="HTML",
                text="⏰ <b>Obunangiz tugadi!</b>\n\nKanaldan chiqarildingiz. (Qayta kira olasiz ✅)\n"
                     "Davom etish uchun yangi to'lov qiling 👉 /start")
            db_deactivate(sub_id)
        except Exception as e: logger.warning(f"Kick {uid}: {e}")

    for sid, uid, end in db_warn_subs(7, "warned_7"):
        try:
            await context.bot.send_message(chat_id=uid, parse_mode="HTML",
                text=f"⚠️ <b>Obunangiz {datetime.fromisoformat(end).strftime('%d.%m.%Y')} da tugaydi!</b>\n\n"
                     f"📅 7 kun qoldi. Uzilmaslik uchun yangi to'lov qiling 👉 /start")
            db_mark_warn(sid, "warned_7")
        except Exception as e: logger.warning(f"7d {uid}: {e}")

    for sid, uid, end in db_warn_subs(3, "warned_3"):
        try:
            await context.bot.send_message(chat_id=uid, parse_mode="HTML",
                text=f"⚠️ <b>Obunangiz {datetime.fromisoformat(end).strftime('%d.%m.%Y')} da tugaydi!</b>\n\n"
                     f"📅 3 kun qoldi. Zudlik bilan to'lov qiling 👉 /start")
            db_mark_warn(sid, "warned_3")
        except Exception as e: logger.warning(f"3d {uid}: {e}")

    for sid, uid, end in db_warn_subs(1, "warned_1"):
        try:
            await context.bot.send_message(chat_id=uid, parse_mode="HTML",
                text=f"🔴 <b>DIQQAT! Obunangiz ertaga ({datetime.fromisoformat(end).strftime('%d.%m.%Y')}) tugaydi!</b>\n\n"
                     f"⏰ Faqat 1 kun qoldi! Darhol yangi to'lov qiling 👉 /start")
            db_mark_warn(sid, "warned_1")
        except Exception as e: logger.warning(f"1d {uid}: {e}")


# ═══════════════════════════════════════════════════
#                     MAIN
# ═══════════════════════════════════════════════════
async def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_video))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_handler(CallbackQueryHandler(cb_pay,   pattern=r"^pay_"))
    app.add_handler(CallbackQueryHandler(cb_chek,  pattern=r"^chk_"))
    app.add_handler(CallbackQueryHandler(cb_admin,
        pattern=r"^(m_|s_|pt_|pb_|pd_|su_|sp_|tu_|se_|ch_|noop)"))

    app.job_queue.run_repeating(job_subs, interval=CHECK_INTERVAL, first=120)

    logger.info("✅ Bot ishga tushdi!")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
PYEOF
cp /tmp/bot_v3.py /mnt/user-data/outputs/main.py
printf 'python-telegram-bot[job-queue]==21.6\n' > /mnt/user-data/outputs/requirements.txt
echo "Done - $(wc -l < /mnt/user-data/outputs/main.py) qator"
