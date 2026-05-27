import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ═══════════════════════════════════════════════
#                  SOZLAMALAR
# ═══════════════════════════════════════════════
BOT_TOKEN  = "8485655940:AAE0iMKVKYz8x3iITIR4zhxZv9mmuXvaz9A"
OWNER_ID   = 6857570089
CHANNEL_ID = -1003897588293

MONTH_LABEL = {
    "1":  "1 Oylik  — 25,000 so'm",
    "3":  "3 Oylik  — 50,000 so'm",
    "6":  "6 Oylik  — 100,000 so'm",
    "12": "1 Yillik — 250,000 so'm",
}
MONTH_DELTA = {"1": 1, "3": 3, "6": 6, "12": 12}

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Admin doimiy klaviatura ──────────────────────
ADMIN_KB = ReplyKeyboardMarkup(
    [
        ["📊 Statistika",       "👥 Foydalanuvchilar"],
        ["📢 Xabar Yuborish",   "📝 Post Yaratish"],
        ["➕ Admin Qo'shish",   "➖ Admin O'chirish"],
        ["📋 Adminlar Ro'yxati"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


# ═══════════════════════════════════════════════
#                   DATABASE
# ═══════════════════════════════════════════════
def init_db():
    with sqlite3.connect("bot.db") as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT,
            full_name TEXT, joined_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY, added_at TEXT)""")
        c.execute("INSERT OR IGNORE INTO admins (admin_id, added_at) VALUES (?,?)",
                  (OWNER_ID, datetime.now().isoformat()))
        conn.commit()

def db_add_user(user_id, username, full_name):
    with sqlite3.connect("bot.db") as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id,username,full_name,joined_at) VALUES (?,?,?,?)",
            (user_id, username or "", full_name or "", datetime.now().isoformat()))

def db_get_all_user_ids():
    with sqlite3.connect("bot.db") as conn:
        return [r[0] for r in conn.execute("SELECT user_id FROM users").fetchall()]

def db_get_user_count():
    with sqlite3.connect("bot.db") as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

def db_get_today_count():
    today = datetime.now().date().isoformat()
    with sqlite3.connect("bot.db") as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{today}%",)).fetchone()[0]

def db_get_week_count():
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    with sqlite3.connect("bot.db") as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at >= ?", (week_ago,)).fetchone()[0]

def db_get_admins():
    with sqlite3.connect("bot.db") as conn:
        return [r[0] for r in conn.execute("SELECT admin_id FROM admins").fetchall()]

def db_add_admin(admin_id):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("INSERT OR IGNORE INTO admins (admin_id,added_at) VALUES (?,?)",
                     (admin_id, datetime.now().isoformat()))

def db_remove_admin(admin_id):
    with sqlite3.connect("bot.db") as conn:
        conn.execute("DELETE FROM admins WHERE admin_id=?", (admin_id,))

def is_admin(user_id):
    return user_id == OWNER_ID or user_id in db_get_admins()


# ═══════════════════════════════════════════════
#                    /START
# ═══════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_add_user(user.id, user.username, user.full_name)

    await update.message.reply_text(
        "🎬 <b>X-DUBBING PREMIUM HAQIDA MALUMOT!</b>\n\n"
        "Bu pullik kanal bo'lib faqat pul to'lab kirishingiz mumkin 💳\n\n"
        "<b>WERX PREMIUM NARXI:</b>\n"
        "💎 1 Oylik = 25 Ming\n"
        "💎 3 Oylik = 50 Ming\n"
        "💎 6 Oylik = 100 Ming\n"
        "💎 1 Yillik = 250 Ming\n\n"
        "‼️ <i>Chekni Yuborgach Biroz Kuting. Odatda 5-15 Daqiqada Javob olasiz."
        " Ammo Hayot mamot masalalari bilan bo'lib qolgan paytlar 6-12 soatgacha"
        " kutishga to'g'ri kelishi mumkin. Albatta bunaqasi kam bo'ladi</i> ‼️",
        parse_mode="HTML",
    )

    await update.message.reply_text(
        "Pastdagi Havolaga bosing va Qo'shilish so'rovini yuboring!\n"
        "Keyin esa To'lov qilib rasm yuboring! 👇\n\n"
        '🔗 <a href="https://t.me/+bUQj_WkfOAphNzMy">Kanalga O\'tish</a>\n\n'
        "💳 <b>To'lov Karta Raqami:</b>\n"
        "<code>5614 6816 2654 6851</code>\n"
        "Shaxs: N. F\n\n"
        "📸 <b>Chekni Rasm Formatida Yuboring...</b>",
        parse_mode="HTML",
    )

    # Adminlarga doimiy klaviaturani ko'rsatish
    if is_admin(user.id):
        await update.message.reply_text(
            "👑 <b>Admin paneliga xush kelibsiz!</b>",
            parse_mode="HTML",
            reply_markup=ADMIN_KB,
        )


# ═══════════════════════════════════════════════
#               RASM HANDLER
# ═══════════════════════════════════════════════
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Post yaratish jarayonida rasm kelsa
    if is_admin(user.id) and context.user_data.get("mode") == "post_photo":
        context.user_data["post_data"]["photo"] = update.message.photo[-1].file_id
        context.user_data["mode"] = "post_text"
        await update.message.reply_text(
            "✅ Rasm qabul qilindi!\n\n"
            "2️⃣ Matn kiriting:\n"
            "<i>(/skip — matnsiz davom etish)</i>",
            parse_mode="HTML",
        )
        return

    # Oddiy foydalanuvchi chek yuborganda
    await update.message.reply_text(
        "⏳ <b>Tasdiqlash Jarayonida...</b>\n\n"
        "Adminlar chekingizni tekshirmoqda, biroz kuting!",
        parse_mode="HTML",
    )

    keyboard = [
        [InlineKeyboardButton("💎 1 Oylik (25K)",  callback_data=f"ok_1_{user.id}"),
         InlineKeyboardButton("💎 3 Oylik (50K)",  callback_data=f"ok_3_{user.id}")],
        [InlineKeyboardButton("💎 6 Oylik (100K)", callback_data=f"ok_6_{user.id}"),
         InlineKeyboardButton("💎 1 Yillik (250K)",callback_data=f"ok_12_{user.id}")],
        [InlineKeyboardButton("❌ Rad Etish",       callback_data=f"rad_{user.id}")],
    ]
    username_str = f"@{user.username}" if user.username else "Yo'q"
    caption = (
        f"📸 <b>Yangi Chek Keldi!</b>\n\n"
        f"👤 Ism: {user.full_name}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📱 Username: {username_str}\n\n"
        f"Chekni tekshirib, mos obuna turini tanlang 👇"
    )
    for admin_id in db_get_admins():
        try:
            await context.bot.forward_message(
                chat_id=admin_id, from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id)
            await context.bot.send_message(
                chat_id=admin_id, text=caption, parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.warning(f"Admin {admin_id} xato: {e}")


# ═══════════════════════════════════════════════
#           CALLBACK — CHEK TASDIQLASH
# ═══════════════════════════════════════════════
async def callback_chek(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.answer("Ruxsat yoq!", show_alert=True)
        return

    parts   = query.data.split("_")
    action  = parts[0]
    user_id = int(parts[-1])

    if action == "ok":
        months_str = parts[1]
        months_int = MONTH_DELTA[months_str]
        label      = MONTH_LABEL[months_str]
        try:
            await context.bot.approve_chat_join_request(chat_id=CHANNEL_ID, user_id=user_id)
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ <b>Tabriklaymiz!</b>\n\n"
                    f"💎 <b>{label}</b> obunangiz tasdiqlandi!\n\n"
                    f"Kanalga muvaffaqiyatli qo'shildingiz! Xush kelibsiz 🎉"
                ),
                parse_mode="HTML",
            )
            await query.edit_message_text(
                f"✅ <b>Tasdiqlandi!</b>\n👤 <code>{user_id}</code>\n💎 <b>{label}</b>",
                parse_mode="HTML",
            )
        except Exception as e:
            await query.edit_message_text(f"Xato:\n<code>{e}</code>", parse_mode="HTML")

    elif action == "rad":
        try:
            await context.bot.decline_chat_join_request(chat_id=CHANNEL_ID, user_id=user_id)
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ <b>Chekingiz tasdiqlanmadi.</b>\n\nIltimos, to'g'ri chek yuboring.",
                parse_mode="HTML",
            )
            await query.edit_message_text(f"❌ Rad — <code>{user_id}</code>", parse_mode="HTML")
        except Exception as e:
            await query.edit_message_text(f"Xato:\n<code>{e}</code>", parse_mode="HTML")


# ═══════════════════════════════════════════════
#         CALLBACK — POST MANZIL TANLASH
# ═══════════════════════════════════════════════
async def callback_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    data = query.data

    if data == "post_cancel":
        context.user_data.pop("post_data", None)
        context.user_data.pop("mode", None)
        await query.edit_message_text("❌ Post bekor qilindi.")
        return

    await query.edit_message_text("⏳ Yuborilmoqda...")

    post    = context.user_data.get("post_data", {})
    photo   = post.get("photo")
    text    = post.get("text", "")
    buttons = post.get("buttons", [])
    markup  = InlineKeyboardMarkup(buttons) if buttons else None

    ok = fail = 0
    send_channel = data in ("post_channel", "post_both")
    send_users   = data in ("post_users",   "post_both")

    if send_channel:
        try:
            if photo:
                await context.bot.send_photo(
                    chat_id=CHANNEL_ID, photo=photo,
                    caption=text or None, reply_markup=markup, parse_mode="HTML")
            else:
                await context.bot.send_message(
                    chat_id=CHANNEL_ID, text=text,
                    reply_markup=markup, parse_mode="HTML")
            ok += 1
        except Exception as e:
            logger.warning(f"Kanal post xato: {e}")
            fail += 1

    if send_users:
        for uid in db_get_all_user_ids():
            try:
                if photo:
                    await context.bot.send_photo(
                        chat_id=uid, photo=photo,
                        caption=text or None, reply_markup=markup, parse_mode="HTML")
                else:
                    await context.bot.send_message(
                        chat_id=uid, text=text,
                        reply_markup=markup, parse_mode="HTML")
                ok += 1
            except Exception:
                fail += 1

    context.user_data.pop("post_data", None)
    context.user_data.pop("mode", None)

    target_map = {
        "post_channel": "📢 Kanal",
        "post_users":   "👥 Foydalanuvchilar",
        "post_both":    "📢 Kanal + 👥 Foydalanuvchilar",
    }
    await query.edit_message_text(
        f"✅ <b>Post yuborildi!</b>\n\n"
        f"📍 {target_map.get(data, '')}\n"
        f"✅ Muvaffaqiyatli: {ok}\n❌ Xato: {fail}",
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════
#              POST MANZIL TANLASH HELPER
# ═══════════════════════════════════════════════
async def show_post_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post    = context.user_data.get("post_data", {})
    photo   = post.get("photo")
    text    = post.get("text", "")
    buttons = post.get("buttons", [])

    summary = (
        "👁 <b>Post tayyor!</b>\n\n"
        f"🖼 Rasm: {'✅ bor' if photo else '❌ yo\'q'}\n"
        f"📝 Matn: {'✅ bor' if text else '❌ yo\'q'}\n"
        f"🔘 Tugmalar: {len(buttons)} ta\n\n"
        "📍 <b>Qayerga yuborish?</b>"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Kanalga",            callback_data="post_channel"),
         InlineKeyboardButton("👥 Foydalanuvchilarga", callback_data="post_users")],
        [InlineKeyboardButton("🌐 Kanal + Foydalanuvchilar", callback_data="post_both")],
        [InlineKeyboardButton("❌ Bekor qilish",        callback_data="post_cancel")],
    ])
    await update.message.reply_text(summary, parse_mode="HTML", reply_markup=keyboard)


# ═══════════════════════════════════════════════
#                 /SKIP KOMANDA
# ═══════════════════════════════════════════════
async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    mode = context.user_data.get("mode")

    if mode == "post_photo":
        context.user_data["mode"] = "post_text"
        await update.message.reply_text(
            "2️⃣ Matn kiriting:\n<i>(/skip — matnsiz davom etish)</i>",
            parse_mode="HTML")

    elif mode == "post_text":
        context.user_data["post_data"]["text"] = ""
        context.user_data["mode"] = "post_buttons"
        await ask_buttons(update)

    elif mode == "post_buttons":
        context.user_data["post_data"]["buttons"] = []
        context.user_data["mode"] = "post_target"
        await show_post_target(update, context)


async def ask_buttons(update: Update):
    await update.message.reply_text(
        "3️⃣ Tugmalar kiriting:\n\n"
        "Har qatorda: <code>Tugma nomi|https://havola</code>\n\n"
        "📌 Misol:\n"
        "<code>▶️ Tomosha qilish|https://t.me/uzdubgo\n"
        "💎 Premium kanal|https://t.me/+bUQj_WkfOAphNzMy\n"
        "📱 Ilova|https://t.me/uzdubgo</code>\n\n"
        "<i>(/skip — tugmasiz davom etish)</i>",
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════
#                  MATN HANDLER
# ═══════════════════════════════════════════════
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text    = update.message.text.strip()

    if not is_admin(user_id):
        return

    # ── Doimiy klaviatura tugmalari ─────────────
    if text == "📊 Statistika":
        total = db_get_user_count()
        today = db_get_today_count()
        week  = db_get_week_count()
        await update.message.reply_text(
            f"📊 <b>Statistika</b>\n\n"
            f"👥 Jami foydalanuvchilar: <b>{total} ta</b>\n"
            f"📅 Bugun qo'shilganlar:  <b>{today} ta</b>\n"
            f"📆 Haftalik yangilar:     <b>{week} ta</b>",
            parse_mode="HTML")
        return

    if text == "👥 Foydalanuvchilar":
        count = db_get_user_count()
        await update.message.reply_text(
            f"👥 Jami: <b>{count} ta</b> foydalanuvchi", parse_mode="HTML")
        return

    if text == "📢 Xabar Yuborish":
        context.user_data["mode"] = "broadcast"
        await update.message.reply_text(
            "📢 <b>Xabar yozing:</b>\n\nBarcha foydalanuvchilarga yuboriladigan xabarni kiriting:",
            parse_mode="HTML")
        return

    if text == "📝 Post Yaratish":
        context.user_data["mode"] = "post_photo"
        context.user_data["post_data"] = {}
        await update.message.reply_text(
            "📝 <b>Post yaratish!</b>\n\n"
            "1️⃣ Rasm yuboring:\n"
            "<i>(/skip — rasmsiz davom etish)</i>",
            parse_mode="HTML")
        return

    if text == "➕ Admin Qo'shish":
        context.user_data["mode"] = "addadmin"
        await update.message.reply_text(
            "➕ Yangi admin <b>Telegram ID</b>sini kiriting:", parse_mode="HTML")
        return

    if text == "➖ Admin O'chirish":
        context.user_data["mode"] = "removeadmin"
        await update.message.reply_text(
            "➖ O'chiriladigan admin <b>ID</b>sini kiriting:", parse_mode="HTML")
        return

    if text == "📋 Adminlar Ro'yxati":
        admins = db_get_admins()
        lines  = [f"• <code>{a}</code>{'  👑 Egasi' if a == OWNER_ID else ''}" for a in admins]
        await update.message.reply_text(
            "📋 <b>Adminlar:</b>\n\n" + "\n".join(lines), parse_mode="HTML")
        return

    # ── Mode asosidagi inputlar ─────────────────
    mode = context.user_data.get("mode")

    if mode == "post_text":
        context.user_data["post_data"]["text"] = text
        context.user_data["mode"] = "post_buttons"
        await ask_buttons(update)
        return

    if mode == "post_buttons":
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if "|" in line:
                label, url = line.split("|", 1)
                rows.append([InlineKeyboardButton(label.strip(), url=url.strip())])
        context.user_data["post_data"]["buttons"] = rows
        context.user_data["mode"] = "post_target"
        await show_post_target(update, context)
        return

    if mode == "broadcast":
        context.user_data.pop("mode")
        users = db_get_all_user_ids()
        ok = fail = 0
        msg = await update.message.reply_text("📢 Yuborilmoqda...")
        for uid in users:
            try:
                await context.bot.send_message(chat_id=uid, text=text)
                ok += 1
            except Exception:
                fail += 1
        await msg.edit_text(
            f"📢 <b>Yuborildi!</b>\n✅ Muvaffaqiyatli: {ok}\n❌ Xato: {fail}",
            parse_mode="HTML")
        return

    if mode == "addadmin":
        context.user_data.pop("mode")
        try:
            new_id = int(text)
            db_add_admin(new_id)
            await update.message.reply_text(
                f"✅ Admin qo'shildi: <code>{new_id}</code>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Faqat raqam kiriting!")
        return

    if mode == "removeadmin":
        context.user_data.pop("mode")
        try:
            rem_id = int(text)
            if rem_id == OWNER_ID:
                await update.message.reply_text("❌ Bot egasini o'chirib bo'lmaydi!")
            else:
                db_remove_admin(rem_id)
                await update.message.reply_text(
                    f"✅ Admin o'chirildi: <code>{rem_id}</code>", parse_mode="HTML")
        except ValueError:
            await update.message.reply_text("❌ Faqat raqam kiriting!")
        return


# ═══════════════════════════════════════════════
#                     MAIN
# ═══════════════════════════════════════════════
async def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("skip",  cmd_skip))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(callback_chek, pattern=r"^(ok|rad)_"))
    app.add_handler(CallbackQueryHandler(callback_post, pattern=r"^post_"))

    logger.info("✅ Bot ishga tushdi!")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("🟢 Polling boshlandi.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
