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

# ═══════════════════════════════════════════════
#                   SOZLAMALAR
# ═══════════════════════════════════════════════
BOT_TOKEN       = "8485655940:AAE0iMKVKYz8x3iITIR4zhxZv9mmuXvaz9A"
OWNER_ID        = 6857570089
PREMIUM_CHANNEL = -1003897588293
CHECK_INTERVAL  = 6 * 3600  # 6 soatda bir tekshiruv

MONTH_LABEL = {
    "1": "1 Oylik — 25,000 so'm", "3": "3 Oylik — 50,000 so'm",
    "6": "6 Oylik — 100,000 so'm", "12": "1 Yillik — 250,000 so'm",
}
MONTH_DELTA = {"1": 1, "3": 3, "6": 6, "12": 12}

STATE_TO_SETTING = {
    "set_support_phone":    "support_phone",
    "set_support_username": "support_username",
    "set_card_number":      "card_number",
    "set_card_name":        "card_name",
    "set_premium_invite":   "premium_invite",
}

DEFAULT_SETTINGS = {
    "support_phone":    "+998 xx xxx xx xx",
    "support_username": "@username",
    "card_number":      "5614 6816 2654 6851",
    "card_name":        "N. F",
    "premium_invite":   "https://t.me/+bUQj_WkfOAphNzMy",
}

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════
#                   DATABASE
# ═══════════════════════════════════════════════
def init_db():
    with sqlite3.connect("bot.db") as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, joined_at TEXT)""")
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
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT,
            file_id TEXT, file_type TEXT, added_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS saved_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, channel_id TEXT)""")
        for k, v in DEFAULT_SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings (key,value) VALUES (?,?)", (k, v))
        for row in [
            (1, "💎 Premium Kanal",   str(PREMIUM_CHANNEL)),
            (2, "📢 Asosiy Kanal",    "@FxDubbing"),
            (3, "👥 Foydalanuvchilar","users"),
        ]:
            c.execute("INSERT OR IGNORE INTO saved_channels (id,name,channel_id) VALUES (?,?,?)", row)
        c.execute("INSERT OR IGNORE INTO admins (admin_id,added_at) VALUES (?,?)",
                  (OWNER_ID, datetime.now().isoformat()))
        conn.commit()

def get_setting(key):
    with sqlite3.connect("bot.db") as conn:
        r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else DEFAULT_SETTINGS.get(key, "—")

def set_setting(key, value):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value))

def db_add_user(uid, uname, fname):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id,username,full_name,joined_at) VALUES (?,?,?,?)",
                     (uid, uname or "", fname or "", datetime.now().isoformat()))

def db_all_user_ids():
    with sqlite3.connect("bot.db") as conn:
        return [r[0] for r in conn.execute("SELECT user_id FROM users").fetchall()]

def db_user_count():
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

def db_today_count():
    t = datetime.now().date().isoformat()
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{t}%",)).fetchone()[0]

def db_week_count():
    w = (datetime.now()-timedelta(days=7)).isoformat()
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT COUNT(*) FROM users WHERE joined_at>=?", (w,)).fetchone()[0]

def db_get_admins():
    with sqlite3.connect("bot.db") as conn:
        return [r[0] for r in conn.execute("SELECT admin_id FROM admins").fetchall()]

def db_admin_count():
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]

def db_add_admin(aid):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT OR IGNORE INTO admins (admin_id,added_at) VALUES (?,?)",
                     (aid, datetime.now().isoformat()))

def db_remove_admin(aid):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("DELETE FROM admins WHERE admin_id=?", (aid,))

def is_admin(uid): return uid == OWNER_ID or uid in db_get_admins()

def db_add_sub(uid, months):
    s = datetime.now(); e = s + timedelta(days=30*months)
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT INTO subscriptions (user_id,months,start_date,end_date) VALUES (?,?,?,?)",
                     (uid, months, s.isoformat(), e.isoformat()))

def db_active_sub_count():
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT COUNT(*) FROM subscriptions WHERE active=1").fetchone()[0]

def db_active_subs():
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT user_id,months,end_date FROM subscriptions WHERE active=1 ORDER BY end_date").fetchall()

def db_expired_subs():
    now = datetime.now().isoformat()
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT id,user_id FROM subscriptions WHERE active=1 AND end_date<=?", (now,)).fetchall()

def db_warning_subs(days):
    target = (datetime.now()+timedelta(days=days)).isoformat()
    col = f"warned_{days}"
    with sqlite3.connect("bot.db") as conn:
        return conn.execute(
            f"SELECT id,user_id,end_date FROM subscriptions WHERE active=1 AND {col}=0 AND end_date<=?",
            (target,)).fetchall()

def db_mark_warned(sid, days):
    with sqlite3.connect("bot.db") as conn:
        conn.execute(f"UPDATE subscriptions SET warned_{days}=1 WHERE id=?", (sid,))

def db_deactivate_sub(sid):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("UPDATE subscriptions SET active=0 WHERE id=?", (sid,))

def db_get_tutorials():
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT id,title,file_id,file_type FROM tutorials ORDER BY added_at").fetchall()

def db_add_tutorial(title, fid, ftype):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT INTO tutorials (title,file_id,file_type,added_at) VALUES (?,?,?,?)",
                     (title, fid, ftype, datetime.now().isoformat()))

def db_del_tutorial(tid):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("DELETE FROM tutorials WHERE id=?", (tid,))

def db_get_saved_channels():
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT id,name,channel_id FROM saved_channels").fetchall()

def db_add_channel(name, cid):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT INTO saved_channels (name,channel_id) VALUES (?,?)", (name, cid))

def db_del_channel(cid):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("DELETE FROM saved_channels WHERE id=?", (cid,))


# ═══════════════════════════════════════════════
#                  KLAVIATURALAR
# ═══════════════════════════════════════════════
USER_KB = ReplyKeyboardMarkup(
    [["💎 Premium Kanal", "📞 Biz Bilan Bog'lanish"], ["📖 Bot Qo'llanmasi"]],
    resize_keyboard=True, is_persistent=True)

ADMIN_KB = ReplyKeyboardMarkup(
    [["📊 Statistika", "📝 Post Yozish"],
     ["⚙️ Sozlamalar", "💎 Obunalar"],
     ["📚 Darslik",    "👁 Foydalanuvchi Ko'rinishi"]],
    resize_keyboard=True, is_persistent=True)

def kb_stats():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Foydalanuvchilar soni", callback_data="st_users")],
        [InlineKeyboardButton("👮 Adminlar soni",         callback_data="st_count")],
        [InlineKeyboardButton("📋 Adminlar ro'yxati",     callback_data="st_list")],
        [InlineKeyboardButton("➕ Admin qo'shish",        callback_data="st_add"),
         InlineKeyboardButton("➖ Admin o'chirish",       callback_data="st_remove")],
        [InlineKeyboardButton("◀️ Ortga", callback_data="back_home")],
    ])

def kb_post():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔘 Tugmali post",  callback_data="post_btn_yes")],
        [InlineKeyboardButton("📄 Tugmasiz post", callback_data="post_btn_no")],
        [InlineKeyboardButton("◀️ Ortga",         callback_data="back_home")],
    ])

def kb_format():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Rasmli",  callback_data="pfmt_image"),
         InlineKeyboardButton("📝 Matnli", callback_data="pfmt_text")],
        [InlineKeyboardButton("🎵 Ovozli", callback_data="pfmt_voice"),
         InlineKeyboardButton("🎥 Videoli",callback_data="pfmt_video")],
        [InlineKeyboardButton("◀️ Ortga",  callback_data="sec_post")],
    ])

def kb_settings():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Qo'llab-quvvatlash",   callback_data="set_support")],
        [InlineKeyboardButton("💳 Karta ma'lumotlari",   callback_data="set_card")],
        [InlineKeyboardButton("🔗 Premium kanal havolasi",callback_data="set_invite")],
        [InlineKeyboardButton("📢 Saqlangan kanallar",   callback_data="set_channels")],
        [InlineKeyboardButton("◀️ Ortga",                callback_data="back_home")],
    ])

def kb_subs():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Faol obunalar",  callback_data="sub_list")],
        [InlineKeyboardButton("🗑 Qo'lda chiqarish",callback_data="sub_kick")],
        [InlineKeyboardButton("◀️ Ortga",          callback_data="back_home")],
    ])

def kb_tutorials():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Darslik qo'shish",  callback_data="tut_add")],
        [InlineKeyboardButton("📋 Darsliklar ro'yxati",callback_data="tut_list")],
        [InlineKeyboardButton("🗑 Darslik o'chirish",  callback_data="tut_delete_list")],
        [InlineKeyboardButton("◀️ Ortga",             callback_data="back_home")],
    ])

def kb_dest(selected):
    rows = []
    for ch_id, name, _ in db_get_saved_channels():
        check = "✅ " if ch_id in selected else ""
        rows.append([InlineKeyboardButton(f"{check}{name}", callback_data=f"dest_{ch_id}")])
    rows.append([InlineKeyboardButton("📤 Yuborish", callback_data="dest_send")])
    rows.append([InlineKeyboardButton("◀️ Ortga",    callback_data="sec_post")])
    return InlineKeyboardMarkup(rows)

def kb_back(to):
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Ortga", callback_data=to)]])


# ═══════════════════════════════════════════════
#                   /START
# ═══════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_add_user(user.id, user.username, user.full_name)
    context.user_data.clear()
    if is_admin(user.id):
        await update.message.reply_text(
            "👑 <b>Admin paneliga xush kelibsiz!</b>\n\nPastdagi tugmalardan foydalaning:",
            parse_mode="HTML", reply_markup=ADMIN_KB)
    else:
        await update.message.reply_text(
            "Assalom Aleykum Xurmatli Foydalanuvchi! 👋\n\n"
            "Siz <b>X-Dubbing Studiyasining</b> Botidasiz!\n"
            "Bizdan qanday xizmat? Iltimos pastki qatordagi tugmalar orqali murojaat qiling!",
            parse_mode="HTML", reply_markup=USER_KB)

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    context.user_data.clear()
    await update.message.reply_text(
        "👑 <b>Admin Panel</b>", parse_mode="HTML", reply_markup=ADMIN_KB)

async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    state = context.user_data.get("state","")
    post  = context.user_data.get("post", {})
    if state == "post_caption":
        post["caption"] = ""
        context.user_data["post"] = post
        if post.get("has_buttons"):
            context.user_data["state"] = "post_buttons"
            await update.message.reply_text(
                "🔘 <b>Tugmalar kiriting</b> (har qatorda <code>Nom|URL</code>):\n<i>(/skip — tugmasiz)</i>",
                parse_mode="HTML")
        else:
            context.user_data["state"] = "post_dest"
            context.user_data["post"]["destinations"] = []
            await update.message.reply_text(
                "📍 <b>Qayerga yuboramiz?</b>", parse_mode="HTML", reply_markup=kb_dest([]))
    elif state == "post_buttons":
        post["buttons"] = []
        context.user_data["post"] = post
        context.user_data["state"] = "post_dest"
        context.user_data["post"]["destinations"] = []
        await update.message.reply_text(
            "📍 <b>Qayerga yuboramiz?</b>", parse_mode="HTML", reply_markup=kb_dest([]))


# ═══════════════════════════════════════════════
#              FOYDALANUVCHI TUGMALARI
# ═══════════════════════════════════════════════
async def show_premium(update: Update):
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
    invite = get_setting("premium_invite")
    card   = get_setting("card_number")
    cname  = get_setting("card_name")
    await update.message.reply_text(
        "Pastdagi Havolaga bosing va Qo'shilish so'rovini yuboring!\n"
        "Keyin esa To'lov qilib rasm yuboring! 👇\n\n"
        f'🔗 <a href="{invite}">Kanalga O\'tish</a>\n\n'
        f"💳 <b>To'lov Karta Raqami:</b>\n<code>{card}</code>\nShaxs: {cname}\n\n"
        "📸 <b>Chekni Rasm Formatida Yuboring...</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💳 TO'LOV QILISH", callback_data="pay_now")]]))

async def show_support(update: Update):
    phone = get_setting("support_phone")
    uname = get_setting("support_username")
    await update.message.reply_text(
        f"📞 <b>Biz Bilan Bog'lanish</b>\n\n"
        f"Biror Muammo yoki Taklif bo'lsa:\n\n"
        f"📱 {phone}\n💬 {uname}\n\n"
        f"<i>Admin bot kabi 24/7 ishlamaydi! Biroz kutishga to'g'ri kelishi mumkin!</i>",
        parse_mode="HTML")

async def show_tutorials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tuts = db_get_tutorials()
    if not tuts:
        await update.message.reply_text("📚 Hozircha darsliklar mavjud emas.")
        return
    await update.message.reply_text("📖 <b>Bot Qo'llanmasi:</b>", parse_mode="HTML")
    for _, title, fid, ftype in tuts:
        try:
            if ftype == "video":
                await context.bot.send_video(update.effective_chat.id, video=fid, caption=f"📹 {title}")
            elif ftype == "photo":
                await context.bot.send_photo(update.effective_chat.id, photo=fid, caption=f"📸 {title}")
            elif ftype == "document":
                await context.bot.send_document(update.effective_chat.id, document=fid, caption=f"📄 {title}")
        except Exception as e:
            logger.warning(f"Tutorial yuborish xato: {e}")


# ═══════════════════════════════════════════════
#              CHEK / RECEIPT HANDLER
# ═══════════════════════════════════════════════
async def send_receipt_to_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data.pop("state", None)
    await update.message.reply_text(
        "⏳ <b>Tasdiqlash Jarayonida...</b>\n\nAdminlar chekingizni tekshirmoqda!",
        parse_mode="HTML")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 1 Oylik (25K)",  callback_data=f"ok_1_{user.id}"),
         InlineKeyboardButton("💎 3 Oylik (50K)",  callback_data=f"ok_3_{user.id}")],
        [InlineKeyboardButton("💎 6 Oylik (100K)", callback_data=f"ok_6_{user.id}"),
         InlineKeyboardButton("💎 1 Yillik (250K)",callback_data=f"ok_12_{user.id}")],
        [InlineKeyboardButton("❌ Rad Etish",       callback_data=f"rad_{user.id}")],
    ])
    ustr = f"@{user.username}" if user.username else "Yo'q"
    caption = (f"📸 <b>Yangi Chek Keldi!</b>\n\n"
               f"👤 Ism: {user.full_name}\n🆔 ID: <code>{user.id}</code>\n📱 Username: {ustr}")
    for aid in db_get_admins():
        try:
            await context.bot.forward_message(aid, update.effective_chat.id, update.message.message_id)
            await context.bot.send_message(aid, caption, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning(f"Admin {aid}: {e}")


# ═══════════════════════════════════════════════
#              MEDIA HANDLER (Rasm/Ovoz/Video)
# ═══════════════════════════════════════════════
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    msg   = update.message
    state = context.user_data.get("state","")

    # Admin — darslik yuklash
    if is_admin(user.id) and state == "tut_file":
        title = context.user_data.pop("tut_title", "Darslik")
        context.user_data.pop("state", None)
        fid = ftype = None
        if msg.video:    fid, ftype = msg.video.file_id,         "video"
        elif msg.photo:  fid, ftype = msg.photo[-1].file_id,     "photo"
        elif msg.document: fid, ftype = msg.document.file_id,    "document"
        if fid:
            db_add_tutorial(title, fid, ftype)
            await msg.reply_text(f"✅ Darslik qo'shildi: <b>{title}</b>", parse_mode="HTML")
        else:
            await msg.reply_text("❌ Video, rasm yoki fayl yuboring!")
        return

    # Admin — post yaratish
    if is_admin(user.id) and state == "post_content":
        post = context.user_data.get("post", {})
        fmt  = post.get("format")
        ok   = False
        if fmt == "image" and msg.photo:
            post["content"] = msg.photo[-1].file_id
            post["caption"] = msg.caption or ""
            ok = True
        elif fmt == "voice" and msg.voice:
            post["content"] = msg.voice.file_id
            post["caption"] = msg.caption or ""
            ok = True
        elif fmt == "video" and msg.video:
            post["content"] = msg.video.file_id
            post["caption"] = msg.caption or ""
            ok = True
        if not ok:
            fmt_names = {"image":"rasm 🖼","voice":"ovozli xabar 🎵","video":"video 🎥"}
            await msg.reply_text(f"❌ Iltimos {fmt_names.get(fmt,'')} yuboring!")
            return
        context.user_data["post"] = post
        if post.get("has_buttons"):
            context.user_data["state"] = "post_buttons"
            await msg.reply_text(
                "🔘 <b>Tugmalar kiriting</b> (har qatorda <code>Nom|URL</code>):\n<i>(/skip — tugmasiz)</i>",
                parse_mode="HTML")
        else:
            context.user_data["state"] = "post_dest"
            post["destinations"] = []
            await msg.reply_text("📍 <b>Qayerga yuboramiz?</b>",
                                  parse_mode="HTML", reply_markup=kb_dest([]))
        return

    # Oddiy foydalanuvchi — chek rasmi
    if not is_admin(user.id) and msg.photo:
        await send_receipt_to_admins(update, context)


# ═══════════════════════════════════════════════
#              MATN HANDLER
# ═══════════════════════════════════════════════
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user  = update.effective_user
    text  = update.message.text.strip()
    state = context.user_data.get("state","")

    # ── FOYDALANUVCHI ───────────────────────────
    if not is_admin(user.id):
        if state == "waiting_payment":
            await update.message.reply_text("📸 Iltimos, <b>rasm</b> ko'rinishida chek yuboring!",
                                             parse_mode="HTML")
            return
        if text == "💎 Premium Kanal":       await show_premium(update)
        elif text == "📞 Biz Bilan Bog'lanish": await show_support(update)
        elif text == "📖 Bot Qo'llanmasi":    await show_tutorials(update, context)
        return

    # ── ADMIN ───────────────────────────────────

    # Asosiy tugmalar
    if text == "📊 Statistika":
        await update.message.reply_text("📊 <b>Statistika bo'limi</b>",
                                         parse_mode="HTML", reply_markup=kb_stats())
        return
    if text == "📝 Post Yozish":
        await update.message.reply_text("📝 <b>Post Yozish</b>\nPost turini tanlang:",
                                         parse_mode="HTML", reply_markup=kb_post())
        return
    if text == "⚙️ Sozlamalar":
        await update.message.reply_text("⚙️ <b>Sozlamalar</b>",
                                         parse_mode="HTML", reply_markup=kb_settings())
        return
    if text == "💎 Obunalar":
        total = db_active_sub_count()
        await update.message.reply_text(
            f"💎 <b>Obunalar bo'limi</b>\n\nFaol obunalar: <b>{total} ta</b>",
            parse_mode="HTML", reply_markup=kb_subs())
        return
    if text == "📚 Darslik":
        await update.message.reply_text("📚 <b>Darslik bo'limi</b>",
                                         parse_mode="HTML", reply_markup=kb_tutorials())
        return
    if text == "👁 Foydalanuvchi Ko'rinishi":
        context.user_data["state"] = "user_view"
        await update.message.reply_text(
            "👁 Foydalanuvchi ko'rinishi. Qaytish uchun /admin yozing.",
            reply_markup=USER_KB)
        return

    # ── Holat asosidagi inputlar ────────────────

    # Settings
    if state in STATE_TO_SETTING:
        key = STATE_TO_SETTING[state]
        set_setting(key, text)
        context.user_data.pop("state")
        await update.message.reply_text(f"✅ Saqlandi: <code>{text}</code>", parse_mode="HTML")
        return

    # Admin qo'shish/o'chirish
    if state == "add_admin":
        context.user_data.pop("state")
        try:
            new_id = int(text)
            db_add_admin(new_id)
            await update.message.reply_text(f"✅ Admin qo'shildi: <code>{new_id}</code>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Faqat raqam kiriting!")
        return

    if state == "remove_admin":
        context.user_data.pop("state")
        try:
            rem_id = int(text)
            if rem_id == OWNER_ID:
                await update.message.reply_text("❌ Bot egasini o'chirib bo'lmaydi!")
            else:
                db_remove_admin(rem_id)
                await update.message.reply_text(f"✅ Admin o'chirildi: <code>{rem_id}</code>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Faqat raqam kiriting!")
        return

    # Qo'lda chiqarish
    if state == "kick_user":
        context.user_data.pop("state")
        try:
            kick_id = int(text)
            await context.bot.ban_chat_member(chat_id=PREMIUM_CHANNEL, user_id=kick_id)
            await context.bot.unban_chat_member(chat_id=PREMIUM_CHANNEL, user_id=kick_id)
            try:
                await context.bot.send_message(
                    kick_id,
                    "⚠️ <b>Obunangiz bekor qilindi.</b>\n\nKanaldan chiqarildingiz.\nYangi obuna: /start",
                    parse_mode="HTML")
            except Exception:
                pass
            await update.message.reply_text(f"✅ <code>{kick_id}</code> chiqarildi.", parse_mode="HTML")
        except Exception as e:
            err = str(e).lower()
            if "not enough rights" in err or "admin" in err:
                await update.message.reply_text("❌ Bot bu kanalda admin emas yoki yetarli huquqi yo'q!")
            else:
                await update.message.reply_text(f"❌ Xato: <code>{e}</code>", parse_mode="HTML")
        return

    # Kanal qo'shish
    if state == "ch_name":
        context.user_data["ch_name"] = text
        context.user_data["state"] = "ch_id"
        await update.message.reply_text(
            "🔗 Kanal @username yoki ID sini kiriting:\n<i>Misol: @kanalim yoki -1001234567890</i>",
            parse_mode="HTML")
        return

    if state == "ch_id":
        name = context.user_data.pop("ch_name", "Kanal")
        context.user_data.pop("state")
        cid  = text.strip()
        try:
            chat   = await context.bot.get_chat(cid)
            member = await context.bot.get_chat_member(cid, context.bot.id)
            if member.status in ("administrator","creator"):
                db_add_channel(name, cid)
                await update.message.reply_text(f"✅ Kanal qo'shildi: <b>{chat.title}</b>", parse_mode="HTML")
            else:
                await update.message.reply_text("❌ Bot bu kanalda admin emas! Avval bot ni admin qiling.")
        except Exception as e:
            await update.message.reply_text(f"❌ Kanal topilmadi:\n<code>{e}</code>", parse_mode="HTML")
        return

    # Darslik nomi
    if state == "tut_title":
        context.user_data["tut_title"] = text
        context.user_data["state"] = "tut_file"
        await update.message.reply_text(
            "📹 Darslik faylini yuboring (video/rasm/fayl):", parse_mode="HTML")
        return

    # Post — matn kontenti
    if state == "post_content":
        post = context.user_data.get("post", {})
        if post.get("format") == "text":
            post["content"] = text
            context.user_data["post"] = post
            if post.get("has_buttons"):
                context.user_data["state"] = "post_buttons"
                await update.message.reply_text(
                    "🔘 <b>Tugmalar kiriting</b> (har qatorda <code>Nom|URL</code>):\n<i>(/skip — tugmasiz)</i>",
                    parse_mode="HTML")
            else:
                context.user_data["state"] = "post_dest"
                post["destinations"] = []
                await update.message.reply_text("📍 <b>Qayerga yuboramiz?</b>",
                                                 parse_mode="HTML", reply_markup=kb_dest([]))
        return

    # Post — sarlavha
    if state == "post_caption":
        post = context.user_data.get("post", {})
        post["caption"] = text
        context.user_data["post"] = post
        if post.get("has_buttons"):
            context.user_data["state"] = "post_buttons"
            await update.message.reply_text(
                "🔘 <b>Tugmalar kiriting</b> (har qatorda <code>Nom|URL</code>):\n<i>(/skip — tugmasiz)</i>",
                parse_mode="HTML")
        else:
            context.user_data["state"] = "post_dest"
            post["destinations"] = []
            await update.message.reply_text("📍 <b>Qayerga yuboramiz?</b>",
                                             parse_mode="HTML", reply_markup=kb_dest([]))
        return

    # Post — tugmalar
    if state == "post_buttons":
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if "|" in line:
                label, url = line.split("|",1)
                rows.append([InlineKeyboardButton(label.strip(), url=url.strip())])
        post = context.user_data.get("post",{})
        post["buttons"] = rows
        context.user_data["post"] = post
        context.user_data["state"] = "post_dest"
        post["destinations"] = []
        await update.message.reply_text("📍 <b>Qayerga yuboramiz?</b>",
                                         parse_mode="HTML", reply_markup=kb_dest([]))
        return


# ═══════════════════════════════════════════════
#              CALLBACKS
# ═══════════════════════════════════════════════
async def callback_pay_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["state"] = "waiting_payment"
    await q.message.reply_text(
        "💳 <b>To'lov O'tkazmasi</b>\n\nPul o'tkazmasi rasmini yuboring!\n\n⏳ Kutyabman....",
        parse_mode="HTML")


async def callback_chek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        await q.answer("Ruxsat yo'q!", show_alert=True)
        return
    parts = q.data.split("_")
    action, user_id = parts[0], int(parts[-1])
    if action == "ok":
        ms  = parts[1]
        mi  = MONTH_DELTA[ms]
        lbl = MONTH_LABEL[ms]
        end = (datetime.now()+timedelta(days=30*mi)).strftime("%d.%m.%Y")
        try:
            await context.bot.approve_chat_join_request(PREMIUM_CHANNEL, user_id)
            db_add_sub(user_id, mi)
            await context.bot.send_message(
                user_id,
                f"✅ <b>Tabriklaymiz!</b>\n\n💎 <b>{lbl}</b> obunangiz tasdiqlandi!\n"
                f"📅 Tugash sanasi: <b>{end}</b>\n\nXush kelibsiz 🎉",
                parse_mode="HTML")
            await q.edit_message_text(
                f"✅ <b>Tasdiqlandi!</b>\n👤 <code>{user_id}</code>\n💎 <b>{lbl}</b>\n📅 <b>{end}</b>",
                parse_mode="HTML")
        except Exception as e:
            err = str(e).upper()
            if "HIDE_REQUESTER_MISSING" in err:
                await q.edit_message_text(
                    "❌ <b>Ariza topilmadi!</b>\n\n"
                    "Foydalanuvchi avval kanalga <b>qo'shilish arizasini</b> yuborishi kerak!\n"
                    "Kanal havolasini bosib, ariza yuborsin — keyin siz tasdiqlaysiz.",
                    parse_mode="HTML")
            elif "NOT_ENOUGH_RIGHTS" in err or "ADMIN" in err:
                await q.edit_message_text("❌ Bot kanalda admin emas yoki yetarli huquqi yo'q!", parse_mode="HTML")
            else:
                await q.edit_message_text(f"❌ Xato: <code>{e}</code>", parse_mode="HTML")
    elif action == "rad":
        try:
            await context.bot.decline_chat_join_request(PREMIUM_CHANNEL, user_id)
            await context.bot.send_message(user_id,
                "❌ <b>Chekingiz tasdiqlanmadi.</b>\n\nTo'g'ri chek yuboring.", parse_mode="HTML")
            await q.edit_message_text(f"❌ Rad — <code>{user_id}</code>", parse_mode="HTML")
        except Exception as e:
            await q.edit_message_text(f"❌ Xato: <code>{e}</code>", parse_mode="HTML")


async def callback_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    d   = q.data
    uid = q.from_user.id
    if not is_admin(uid): return

    # ── Ortga / Asosiy ───────────────────────────
    if d == "back_home":
        context.user_data.clear()
        await q.edit_message_text("👑 <b>Admin Panel</b> — pastdagi tugmalardan foydalaning.",
                                   parse_mode="HTML")
        return

    # ── Statistika ───────────────────────────────
    if d == "sec_stats":
        await q.edit_message_text("📊 <b>Statistika bo'limi</b>",
                                   parse_mode="HTML", reply_markup=kb_stats())
    elif d == "st_users":
        await q.edit_message_text(
            f"👥 <b>Foydalanuvchilar</b>\n\nJami: <b>{db_user_count()} ta</b>\n"
            f"Bugun: <b>{db_today_count()} ta</b>\nHaftalik: <b>{db_week_count()} ta</b>",
            parse_mode="HTML", reply_markup=kb_back("sec_stats"))
    elif d == "st_count":
        await q.edit_message_text(f"👮 <b>Adminlar soni: {db_admin_count()} ta</b>",
                                   parse_mode="HTML", reply_markup=kb_back("sec_stats"))
    elif d == "st_list":
        admins = db_get_admins()
        lines  = [f"• <code>{a}</code>{'  👑 Egasi' if a==OWNER_ID else ''}" for a in admins]
        await q.edit_message_text("📋 <b>Adminlar:</b>\n\n"+"\n".join(lines),
                                   parse_mode="HTML", reply_markup=kb_back("sec_stats"))
    elif d == "st_add":
        context.user_data["state"] = "add_admin"
        await q.edit_message_text("➕ Yangi admin <b>Telegram ID</b>sini yuboring:", parse_mode="HTML")
    elif d == "st_remove":
        context.user_data["state"] = "remove_admin"
        await q.edit_message_text("➖ O'chiriladigan admin <b>ID</b>sini yuboring:", parse_mode="HTML")

    # ── Post ─────────────────────────────────────
    elif d == "sec_post":
        context.user_data.pop("post", None)
        context.user_data.pop("state", None)
        await q.edit_message_text("📝 <b>Post Yozish</b>\nTurini tanlang:",
                                   parse_mode="HTML", reply_markup=kb_post())
    elif d in ("post_btn_yes","post_btn_no"):
        context.user_data["post"] = {"has_buttons": d=="post_btn_yes"}
        await q.edit_message_text("📋 <b>Formatni tanlang:</b>",
                                   parse_mode="HTML", reply_markup=kb_format())
    elif d.startswith("pfmt_"):
        fmt = d[5:]
        context.user_data["post"]["format"] = fmt
        context.user_data["state"] = "post_content"
        prompts = {"image":"🖼 <b>Rasm yuboring:</b>","text":"📝 <b>Matn kiriting:</b>",
                   "voice":"🎵 <b>Ovozli xabar yuboring:</b>","video":"🎥 <b>Video yuboring:</b>"}
        await q.edit_message_text(prompts.get(fmt,"Kontent yuboring:"), parse_mode="HTML")

    # ── Destination ──────────────────────────────
    elif d.startswith("dest_") and d != "dest_send":
        ch_id = int(d.split("_")[1])
        dests = context.user_data["post"].get("destinations",[])
        if ch_id in dests: dests.remove(ch_id)
        else: dests.append(ch_id)
        context.user_data["post"]["destinations"] = dests
        await q.edit_message_text("📍 <b>Qayerga yuboramiz?</b>",
                                   parse_mode="HTML", reply_markup=kb_dest(dests))

    elif d == "dest_send":
        dests = context.user_data["post"].get("destinations",[])
        if not dests:
            await q.answer("❌ Kamida bitta joy tanlang!", show_alert=True)
            return
        await q.edit_message_text("⏳ Yuborilmoqda...")
        saved = {row[0]:row[2] for row in db_get_saved_channels()}
        post  = context.user_data.get("post",{})
        fmt   = post.get("format")
        cont  = post.get("content")
        cap   = post.get("caption","") or None
        btns  = post.get("buttons",[])
        markup= InlineKeyboardMarkup(btns) if btns else None
        ok = fail = 0
        errors = []
        for did in dests:
            cid = saved.get(did)
            if not cid: continue
            targets = db_all_user_ids() if cid=="users" else [int(cid) if str(cid).lstrip("-").isdigit() else cid]
            for t in targets:
                try:
                    if fmt=="text":    await context.bot.send_message(t,cont,reply_markup=markup,parse_mode="HTML")
                    elif fmt=="image": await context.bot.send_photo(t,cont,caption=cap,reply_markup=markup,parse_mode="HTML")
                    elif fmt=="voice": await context.bot.send_voice(t,cont,caption=cap,reply_markup=markup)
                    elif fmt=="video": await context.bot.send_video(t,cont,caption=cap,reply_markup=markup,parse_mode="HTML")
                    ok += 1
                except Exception as e:
                    err = str(e).lower()
                    if "not enough rights" in err or "admin" in err:
                        errors.append(f"<code>{t}</code> — Bot admin emas!")
                    fail += 1
        context.user_data.pop("post",None); context.user_data.pop("state",None)
        result = f"✅ <b>Yuborildi!</b>\n✅ Muvaffaqiyatli: {ok}\n❌ Xato: {fail}"
        if errors: result += "\n\n⚠️ <b>Xatolar:</b>\n" + "\n".join(errors[:5])
        await q.edit_message_text(result, parse_mode="HTML")

    # ── Sozlamalar ───────────────────────────────
    elif d == "sec_settings":
        await q.edit_message_text("⚙️ <b>Sozlamalar</b>",
                                   parse_mode="HTML", reply_markup=kb_settings())
    elif d == "set_support":
        phone = get_setting("support_phone"); uname = get_setting("support_username")
        await q.edit_message_text(
            f"📞 <b>Qo'llab-quvvatlash</b>\n\n📱 Telefon: <code>{phone}</code>\n💬 Username: <code>{uname}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📱 Telefon o'zgartirish",  callback_data="edit_phone")],
                [InlineKeyboardButton("💬 Username o'zgartirish", callback_data="edit_uname")],
                [InlineKeyboardButton("◀️ Ortga", callback_data="sec_settings")],
            ]))
    elif d == "edit_phone":
        context.user_data["state"] = "set_support_phone"
        await q.edit_message_text("📱 Yangi telefon raqami kiriting:\n<i>+998 91 123 45 67</i>", parse_mode="HTML")
    elif d == "edit_uname":
        context.user_data["state"] = "set_support_username"
        await q.edit_message_text("💬 Yangi username kiriting:\n<i>@username</i>", parse_mode="HTML")
    elif d == "set_card":
        card = get_setting("card_number"); cname = get_setting("card_name")
        await q.edit_message_text(
            f"💳 <b>Karta Ma'lumotlari</b>\n\nRaqam: <code>{card}</code>\nEgasi: {cname}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Raqamni o'zgartirish", callback_data="edit_card_num")],
                [InlineKeyboardButton("👤 Egasini o'zgartirish", callback_data="edit_card_name")],
                [InlineKeyboardButton("◀️ Ortga", callback_data="sec_settings")],
            ]))
    elif d == "edit_card_num":
        context.user_data["state"] = "set_card_number"
        await q.edit_message_text("💳 Yangi karta raqami kiriting:")
    elif d == "edit_card_name":
        context.user_data["state"] = "set_card_name"
        await q.edit_message_text("👤 Karta egasining ismini kiriting:")
    elif d == "set_invite":
        inv = get_setting("premium_invite")
        context.user_data["state"] = "set_premium_invite"
        await q.edit_message_text(f"🔗 <b>Premium Kanal Havolasi</b>\n\nHozirgi: {inv}\n\nYangi havolani kiriting:",
                                   parse_mode="HTML")
    elif d == "set_channels":
        channels = db_get_saved_channels()
        lines = [f"• {n} — <code>{c}</code>" for _,n,c in channels]
        await q.edit_message_text("📢 <b>Saqlangan Kanallar</b>\n\n"+"\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Kanal qo'shish", callback_data="ch_add")],
                [InlineKeyboardButton("➖ Kanal o'chirish", callback_data="ch_del_list")],
                [InlineKeyboardButton("◀️ Ortga", callback_data="sec_settings")],
            ]))
    elif d == "ch_add":
        context.user_data["state"] = "ch_name"
        await q.edit_message_text("📢 Kanal uchun <b>nom</b> kiriting:\n<i>Misol: Yangi Kanal</i>",
                                   parse_mode="HTML")
    elif d == "ch_del_list":
        channels = db_get_saved_channels()
        rows = [[InlineKeyboardButton(f"🗑 {n}", callback_data=f"ch_del_{ci}")] for ci,n,_ in channels if ci>3]
        rows.append([InlineKeyboardButton("◀️ Ortga", callback_data="set_channels")])
        await q.edit_message_text("➖ O'chirish uchun kanalni tanlang:",
                                   reply_markup=InlineKeyboardMarkup(rows))
    elif d.startswith("ch_del_"):
        db_del_channel(int(d.split("_")[-1]))
        await q.edit_message_text("✅ Kanal o'chirildi.",
                                   reply_markup=kb_back("set_channels"))

    # ── Obunalar ─────────────────────────────────
    elif d == "sec_subs":
        await q.edit_message_text(f"💎 <b>Obunalar</b>\nFaol: {db_active_sub_count()} ta",
                                   parse_mode="HTML", reply_markup=kb_subs())
    elif d == "sub_list":
        subs = db_active_subs()
        if not subs:
            await q.edit_message_text("💎 Faol obuna yo'q.", reply_markup=kb_back("sec_subs"))
            return
        lines = [f"• <code>{u}</code> — {m} oy — <b>{datetime.fromisoformat(e).strftime('%d.%m.%Y')}</b>"
                 for u,m,e in subs]
        await q.edit_message_text(f"💎 <b>Faol obunalar ({len(subs)} ta):</b>\n\n"+"\n".join(lines),
                                   parse_mode="HTML", reply_markup=kb_back("sec_subs"))
    elif d == "sub_kick":
        context.user_data["state"] = "kick_user"
        await q.edit_message_text("🗑 Chiqarilishi kerak bo'lgan foydalanuvchi <b>ID</b>sini yuboring:",
                                   parse_mode="HTML")

    # ── Darslik ──────────────────────────────────
    elif d == "sec_tutorials":
        await q.edit_message_text("📚 <b>Darslik bo'limi</b>",
                                   parse_mode="HTML", reply_markup=kb_tutorials())
    elif d == "tut_add":
        context.user_data["state"] = "tut_title"
        await q.edit_message_text("📚 Darslik <b>nomini</b> kiriting:", parse_mode="HTML")
    elif d == "tut_list":
        tuts = db_get_tutorials()
        if not tuts:
            await q.edit_message_text("📚 Darsliklar yo'q.", reply_markup=kb_back("sec_tutorials"))
            return
        lines = [f"• [{t[0]}] {t[1]} ({t[3]})" for t in tuts]
        await q.edit_message_text("📚 <b>Darsliklar:</b>\n\n"+"\n".join(lines),
                                   parse_mode="HTML", reply_markup=kb_back("sec_tutorials"))
    elif d == "tut_delete_list":
        tuts = db_get_tutorials()
        if not tuts:
            await q.edit_message_text("📚 O'chirish uchun darslik yo'q.", reply_markup=kb_back("sec_tutorials"))
            return
        rows = [[InlineKeyboardButton(f"🗑 {t[1]}", callback_data=f"tut_del_{t[0]}")] for t in tuts]
        rows.append([InlineKeyboardButton("◀️ Ortga", callback_data="sec_tutorials")])
        await q.edit_message_text("🗑 O'chiriladigan darslikni tanlang:",
                                   reply_markup=InlineKeyboardMarkup(rows))
    elif d.startswith("tut_del_"):
        db_del_tutorial(int(d.split("_")[-1]))
        await q.edit_message_text("✅ Darslik o'chirildi.", reply_markup=kb_back("sec_tutorials"))


# ═══════════════════════════════════════════════
#              AVTOMATIK TEKSHIRUVLAR
# ═══════════════════════════════════════════════
async def job_auto_kick(context: ContextTypes.DEFAULT_TYPE):
    for sid, uid in db_expired_subs():
        try:
            await context.bot.ban_chat_member(PREMIUM_CHANNEL, uid)
            await context.bot.unban_chat_member(PREMIUM_CHANNEL, uid)  # Doimiy blok emas!
            try:
                await context.bot.send_message(uid,
                    "⏰ <b>Obunangiz tugadi!</b>\n\nKanaldan chiqarildingiz.\nYangilash: /start",
                    parse_mode="HTML")
            except Exception: pass
            db_deactivate_sub(sid)
            logger.info(f"Avto-chiqarildi: {uid}")
        except Exception as e:
            err = str(e).lower()
            if "not enough rights" in err or "admin" in err:
                logger.error(f"Bot kanalda admin emas! {uid}")
            else:
                logger.warning(f"Kick xato {uid}: {e}")

async def job_warn(context: ContextTypes.DEFAULT_TYPE):
    warn_texts = {
        7: "⚠️ <b>Obunangizga 7 kun qoldi!</b>",
        3: "🔔 <b>Obunangizga 3 kun qoldi!</b>",
        1: "🚨 <b>Obunangizga 1 kun qoldi!</b>",
    }
    for days in [7, 3, 1]:
        for sid, uid, end in db_warning_subs(days):
            end_str = datetime.fromisoformat(end).strftime("%d.%m.%Y")
            try:
                await context.bot.send_message(uid,
                    f"{warn_texts[days]}\n\n📅 Tugash: <b>{end_str}</b>\n\n"
                    f"Uzilmaslik uchun yangi to'lov qiling 👉 /start",
                    parse_mode="HTML")
                db_mark_warned(sid, days)
            except Exception as e:
                logger.warning(f"Warn {days}d {uid}: {e}")


# ═══════════════════════════════════════════════
#                     MAIN
# ═══════════════════════════════════════════════
async def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("skip",  cmd_skip))

    app.add_handler(MessageHandler(filters.PHOTO | filters.VOICE | filters.VIDEO | filters.Document.ALL, handle_media))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_handler(CallbackQueryHandler(callback_chek,    pattern=r"^(ok|rad)_"))
    app.add_handler(CallbackQueryHandler(callback_pay_now, pattern=r"^pay_now$"))
    app.add_handler(CallbackQueryHandler(callback_admin))

    app.job_queue.run_repeating(job_auto_kick, interval=CHECK_INTERVAL, first=60)
    app.job_queue.run_repeating(job_warn,      interval=CHECK_INTERVAL, first=120)

    logger.info("✅ Bot ishga tushdi!")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("🟢 Polling boshlandi.")
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
