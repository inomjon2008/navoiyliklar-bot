
import os
import re
import sqlite3
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# SOZLAMALAR
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

ADMIN_ID = 7267416938
DB_NAME = "navoiyliklar.db"

MIN_VIDEO_REWARD = 5_000
MAX_VIDEO_REWARD = 15_000

MIN_WITHDRAW = 5_000


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            full_name TEXT DEFAULT '',
            balance INTEGER DEFAULT 0,
            registered_name TEXT DEFAULT '',
            reserved_balance INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            content TEXT,
            status TEXT DEFAULT 'pending',
            reward INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            card_number TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Eski DB bilan ishlash uchun migration
    cur.execute("PRAGMA table_info(users)")
    user_columns = {row[1] for row in cur.fetchall()}

    if "registered_name" not in user_columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN registered_name TEXT DEFAULT ''"
        )

    if "reserved_balance" not in user_columns:
        cur.execute(
            "ALTER TABLE users ADD COLUMN reserved_balance INTEGER DEFAULT 0"
        )

    cur.execute("PRAGMA table_info(withdrawals)")
    withdrawal_columns = {row[1] for row in cur.fetchall()}

    if "card_number" not in withdrawal_columns:
        cur.execute(
            "ALTER TABLE withdrawals ADD COLUMN card_number TEXT"
        )

    conn.commit()
    conn.close()


# =========================================================
# USER FUNCTIONS
# =========================================================

def save_user(user, registered_name=None):
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO users (
            id,
            username,
            full_name,
            registered_name
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            username = excluded.username,
            full_name = excluded.full_name
    """, (
        user.id,
        user.username or "",
        user.full_name or "",
        registered_name or "",
    ))

    if registered_name:
        cur.execute("""
            UPDATE users
            SET registered_name = ?
            WHERE id = ?
        """, (registered_name, user.id))

    conn.commit()
    conn.close()


def get_user(user_id):
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            username,
            full_name,
            balance,
            registered_name,
            reserved_balance
        FROM users
        WHERE id = ?
    """, (user_id,))

    row = cur.fetchone()
    conn.close()

    return row


def get_balance(user_id):
    user = get_user(user_id)
    return user[3] if user else 0


def get_reserved_balance(user_id):
    user = get_user(user_id)
    return (user[5] or 0) if user else 0


def get_available_balance(user_id):
    balance = get_balance(user_id)
    reserved = get_reserved_balance(user_id)

    return max(0, balance - reserved)


def format_money(amount):
    return f"{amount:,}".replace(",", " ") + " so‘m"


# =========================================================
# CARD
# =========================================================

def normalize_card(card):
    digits = re.sub(r"\D", "", card)

    if len(digits) != 16:
        return None

    return " ".join(
        digits[i:i + 4]
        for i in range(0, 16, 4)
    )


# =========================================================
# MENUS
# =========================================================

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✉️ Oddiy murojaat",
                callback_data="appeal"
            )
        ],
        [
            InlineKeyboardButton(
                "🎥 Video sotaman",
                callback_data="video"
            )
        ],
        [
            InlineKeyboardButton(
                "💰 Balansim",
                callback_data="balance"
            ),
            InlineKeyboardButton(
                "💳 Pul yechish",
                callback_data="withdraw"
            )
        ],
    ])


def admin_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎥 Videolar",
                callback_data="admin_videos"
            ),
            InlineKeyboardButton(
                "✉️ Murojaatlar",
                callback_data="admin_appeals"
            ),
        ],
        [
            InlineKeyboardButton(
                "💳 Pul yechish",
                callback_data="admin_withdrawals"
            ),
            InlineKeyboardButton(
                "👥 Foydalanuvchilar",
                callback_data="admin_users"
            ),
        ],
        [
            InlineKeyboardButton(
                "📊 Statistika",
                callback_data="admin_stats"
            )
        ],
    ])


def video_reward_menu(submission_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "5 000 so‘m",
                callback_data=f"reward:{submission_id}:5000"
            ),
            InlineKeyboardButton(
                "7 500 so‘m",
                callback_data=f"reward:{submission_id}:7500"
            ),
        ],
        [
            InlineKeyboardButton(
                "10 000 so‘m",
                callback_data=f"reward:{submission_id}:10000"
            ),
            InlineKeyboardButton(
                "12 500 so‘m",
                callback_data=f"reward:{submission_id}:12500"
            ),
        ],
        [
            InlineKeyboardButton(
                "15 000 so‘m",
                callback_data=f"reward:{submission_id}:15000"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Rad etish",
                callback_data=f"reject:{submission_id}"
            )
        ],
    ])


def withdrawal_menu(withdrawal_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ To‘landi",
                callback_data=f"pay:{withdrawal_id}"
            ),
            InlineKeyboardButton(
                "❌ Rad etish",
                callback_data=f"cancelpay:{withdrawal_id}"
            )
        ]
    ])


def appeal_menu(submission_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💬 Javob berish",
                callback_data=f"reply:{submission_id}"
            )
        ]
    ])


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    existing = get_user(user.id)

    if not existing:
        save_user(user)

        context.user_data.clear()
        context.user_data["mode"] = "registration"

        await update.message.reply_text(
            "👋 Assalomu alaykum!\n\n"
            "📰 Navoiyliklar.uz botiga xush kelibsiz.\n\n"
            "Botdan foydalanish uchun avval ro‘yxatdan o‘ting.\n\n"
            "👤 Ismingizni yozing:"
        )
        return

    context.user_data.clear()

    await update.message.reply_text(
        "📰 Navoiyliklar.uz\n\n"
        "Assalomu alaykum! 👋\n\n"
        "Bu bot orqali Navoiydagi muhim voqealar, "
        "murojaatlar va eksklyuziv videolarni yuborishingiz mumkin.\n\n"

        "✉️ Oddiy murojaat\n"
        "Savol, taklif, shikoyat yoki voqea haqida xabar.\n\n"

        "🎥 Video sotaman\n"
        "O‘zingiz suratga olgan eksklyuziv va tezkor videolarni yuboring.\n\n"

        "💰 Video uchun to‘lov\n"
        "Tasdiqlangan videolar uchun 5 000 – 15 000 so‘m.\n\n"

        "💳 Pul yechish\n"
        "Yig‘ilgan balansingizni plastik bank kartangizga yechishingiz mumkin.\n\n"

        "⚠️ Oddiy murojaatlar uchun pul to‘lanmaydi.",
        reply_markup=main_menu()
    )


# =========================================================
# BUTTON HANDLER
# =========================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    # =====================================================
    # ODDIY MUROJAAT
    # =====================================================

    if data == "appeal":
        context.user_data.clear()
        context.user_data["mode"] = "appeal"

        await query.message.reply_text(
            "✉️ ODDIY MUROJAAT\n\n"
            "Savol, taklif, shikoyat yoki voqea haqida "
            "xabarni yozing.\n\n"
            "⚠️ Oddiy murojaatlar uchun pul to‘lanmaydi."
        )
        return

    # =====================================================
    # VIDEO
    # =====================================================

    if data == "video":
        context.user_data.clear()
        context.user_data["mode"] = "video"

        await query.message.reply_text(
            "🎥 VIDEO SOTAMAN\n\n"
            "O‘zingiz suratga olgan eksklyuziv yoki tezkor "
            "videoni shu yerga yuboring.\n\n"
            "Masalan:\n"
            "🚗 Avariya\n"
            "🚨 Hodisa\n"
            "🔥 Yong‘in\n"
            "📰 Muhim voqea\n\n"
            "💰 Tasdiqlangan video uchun:\n"
            "5 000 – 15 000 so‘m\n\n"
            "📌 To‘lov miqdorini admin belgilaydi."
        )
        return

    # =====================================================
    # BALANCE
    # =====================================================

    if data == "balance":
        balance = get_balance(user.id)
        reserved = get_reserved_balance(user.id)
        available = get_available_balance(user.id)

        await query.message.reply_text(
            "💰 BALANSINGIZ\n\n"
            f"💵 Umumiy balans: {format_money(balance)}\n"
            f"⏳ Rezerv qilingan: {format_money(reserved)}\n"
            f"✅ Yechish mumkin: {format_money(available)}",
            reply_markup=main_menu()
        )
        return

    # =====================================================
    # WITHDRAW START
    # =====================================================

    if data == "withdraw":
        available = get_available_balance(user.id)

        if available < MIN_WITHDRAW:
            await query.message.reply_text(
                "❌ Pul yechish mumkin emas.\n\n"
                f"💰 Mavjud balans: {format_money(available)}\n"
                f"📌 Minimal summa: {format_money(MIN_WITHDRAW)}",
                reply_markup=main_menu()
            )
            return

        context.user_data.clear()
        context.user_data["mode"] = "withdraw_amount"

        await query.message.reply_text(
            "💳 PUL YECHISH\n\n"
            f"💰 Yechish mumkin: {format_money(available)}\n\n"
            "Qancha pul yechmoqchi ekaningizni yozing.\n\n"
            "Masalan:\n"
            "15000"
        )
        return

    # =====================================================
    # ADMIN PANEL
    # =====================================================

    if data == "admin_panel":
        if user.id != ADMIN_ID:
            await query.answer(
                "❌ Siz admin emassiz.",
                show_alert=True
            )
            return

        await query.message.reply_text(
            "👨‍💼 ADMIN PANEL",
            reply_markup=admin_menu()
        )
        return

    # =====================================================
    # ADMIN STATS
    # =====================================================

    if data == "admin_stats":
        if user.id != ADMIN_ID:
            return

        conn = db()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM users")
        users_count = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*)
            FROM submissions
            WHERE type = 'video'
            AND status = 'pending'
        """)
        pending_videos = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*)
            FROM submissions
            WHERE type = 'appeal'
            AND status = 'pending'
        """)
        pending_appeals = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*)
            FROM withdrawals
            WHERE status = 'pending'
        """)
        pending_withdrawals = cur.fetchone()[0]

        cur.execute("""
            SELECT COALESCE(SUM(balance), 0)
            FROM users
        """)
        total_balance = cur.fetchone()[0]

        cur.execute("""
            SELECT COALESCE(SUM(reward), 0)
            FROM submissions
            WHERE type = 'video'
            AND status = 'approved'
        """)
        total_paid_for_videos = cur.fetchone()[0]

        conn.close()

        await query.message.reply_text(
            "📊 STATISTIKA\n\n"
            f"👥 Foydalanuvchilar: {users_count}\n"
            f"🎥 Kutilayotgan videolar: {pending_videos}\n"
            f"✉️ Kutilayotgan murojaatlar: {pending_appeals}\n"
            f"💳 Kutilayotgan yechishlar: {pending_withdrawals}\n\n"
            f"💰 Umumiy balans: {format_money(total_balance)}\n"
            f"🎥 Videolarga berilgan: {format_money(total_paid_for_videos)}",
            reply_markup=admin_menu()
        )
        return

    # =====================================================
    # ADMIN USERS
    # =====================================================

    if data == "admin_users":
        if user.id != ADMIN_ID:
            return

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                username,
                registered_name,
                balance,
                reserved_balance
            FROM users
            ORDER BY balance DESC
            LIMIT 30
        """)

        users = cur.fetchall()
        conn.close()

        if not users:
            await query.message.reply_text(
                "👥 Foydalanuvchilar yo‘q."
            )
            return

        text = "👥 FOYDALANUVCHILAR\n\n"

        for user_id, username, name, balance, reserved in users:
            username_text = (
                f"@{username}"
                if username
                else "Username yo‘q"
            )

            text += (
                f"👤 {name or 'Ism kiritilmagan'}\n"
                f"🔗 {username_text}\n"
                f"🆔 {user_id}\n"
                f"💰 Balans: {format_money(balance)}\n"
                f"⏳ Rezerv: {format_money(reserved or 0)}\n"
                "──────────────\n"
            )

        await query.message.reply_text(text)
        return

    # =====================================================
    # ADMIN VIDEOS
    # =====================================================

    if data == "admin_videos":
        if user.id != ADMIN_ID:
            return

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                user_id,
                status,
                reward,
                created_at
            FROM submissions
            WHERE type = 'video'
            ORDER BY id DESC
            LIMIT 20
        """)

        rows = cur.fetchall()
        conn.close()

        if not rows:
            await query.message.reply_text(
                "🎥 Videolar mavjud emas."
            )
            return

        text = "🎥 VIDEOLAR\n\n"

        for submission_id, user_id, status, reward, created_at in rows:
            status_text = {
                "pending": "⏳ Kutilmoqda",
                "approved": "✅ Tasdiqlangan",
                "rejected": "❌ Rad etilgan",
            }.get(status, status)

            text += (
                f"🆔 #{submission_id}\n"
                f"👤 User: {user_id}\n"
                f"📌 {status_text}\n"
                f"💰 {format_money(reward)}\n"
                f"🕒 {created_at}\n"
                "──────────────\n"
            )

        await query.message.reply_text(text)
        return

    # =====================================================
    # ADMIN APPEALS
    # =====================================================

    if data == "admin_appeals":
        if user.id != ADMIN_ID:
            return

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                user_id,
                content,
                status,
                created_at
            FROM submissions
            WHERE type = 'appeal'
            ORDER BY id DESC
            LIMIT 20
        """)

        rows = cur.fetchall()
        conn.close()

        if not rows:
            await query.message.reply_text(
                "✉️ Murojaatlar mavjud emas."
            )
            return

        for submission_id, user_id, content, status, created_at in rows:
            status_text = {
                "pending": "⏳ Kutilmoqda",
                "answered": "✅ Javob berilgan",
            }.get(status, status)

            text = (
                "✉️ MUROJAAT\n\n"
                f"🆔 #{submission_id}\n"
                f"👤 User ID: {user_id}\n"
                f"📌 Holat: {status_text}\n"
                f"🕒 {created_at}\n\n"
                f"📝 {content}"
            )

            await query.message.reply_text(
                text,
                reply_markup=appeal_menu(submission_id)
            )

        return

    # =====================================================
    # ADMIN WITHDRAWALS
    # =====================================================

    if data == "admin_withdrawals":
        if user.id != ADMIN_ID:
            return

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                user_id,
                amount,
                card_number,
                status
            FROM withdrawals
            ORDER BY id DESC
            LIMIT 30
        """)

        rows = cur.fetchall()
        conn.close()

        if not rows:
            await query.message.reply_text(
                "💳 Pul yechish so‘rovlari yo‘q."
            )
            return

        for withdrawal_id, user_id, amount, card, status in rows:

            status_text = {
                "pending": "⏳ Kutilmoqda",
                "paid": "✅ To‘langan",
                "rejected": "❌ Rad etilgan",
            }.get(status, status)

            text = (
                "💳 PUL YECHISH\n\n"
                f"🆔 #{withdrawal_id}\n"
                f"👤 User ID: {user_id}\n"
                f"💰 Summa: {format_money(amount)}\n"
                f"💳 Karta: {card or '—'}\n"
                f"📌 Holat: {status_text}"
            )

            keyboard = (
                withdrawal_menu(withdrawal_id)
                if status == "pending"
                else None
            )

            await query.message.reply_text(
                text,
                reply_markup=keyboard
            )

        return

    # =====================================================
    # ADMIN REPLY
    # =====================================================

    if data.startswith("reply:"):
        if user.id != ADMIN_ID:
            return

        try:
            submission_id = int(data.split(":")[1])
        except (ValueError, IndexError):
            return

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            SELECT user_id
            FROM submissions
            WHERE id = ?
            AND type = 'appeal'
        """, (submission_id,))

        row = cur.fetchone()
        conn.close()

        if not row:
            await query.answer(
                "Murojaat topilmadi.",
                show_alert=True
            )
            return

        context.user_data.clear()
        context.user_data["mode"] = "admin_reply"
        context.user_data["reply_submission_id"] = submission_id

        await query.message.reply_text(
            f"💬 #{submission_id}-murojaatga javob yozing:"
        )
        return

    # =====================================================
    # VIDEO REWARD
    # =====================================================

    if data.startswith("reward:"):

        if user.id != ADMIN_ID:
            await query.answer(
                "❌ Siz admin emassiz.",
                show_alert=True
            )
            return

        try:
            _, submission_id, reward = data.split(":")
            submission_id = int(submission_id)
            reward = int(reward)
        except ValueError:
            return

        if not MIN_VIDEO_REWARD <= reward <= MAX_VIDEO_REWARD:
            await query.answer(
                "❌ Noto‘g‘ri summa.",
                show_alert=True
            )
            return

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            SELECT user_id, type, status
            FROM submissions
            WHERE id = ?
        """, (submission_id,))

        row = cur.fetchone()

        if not row:
            conn.close()
            await query.answer(
                "Material topilmadi.",
                show_alert=True
            )
            return

        user_id, submission_type, status = row

        if submission_type != "video":
            conn.close()
            await query.answer(
                "Bu video emas.",
                show_alert=True
            )
            return

        if status != "pending":
            conn.close()
            await query.answer(
                "Bu video allaqachon ko‘rib chiqilgan.",
                show_alert=True
            )
            return

        # Bitta transaction
        cur.execute("""
            UPDATE submissions
            SET status = 'approved',
                reward = ?
            WHERE id = ?
            AND status = 'pending'
        """, (reward, submission_id))

        if cur.rowcount != 1:
            conn.rollback()
            conn.close()
            await query.answer(
                "Video allaqachon ko‘rib chiqilgan.",
                show_alert=True
            )
            return

        cur.execute("""
            UPDATE users
            SET balance = balance + ?
            WHERE id = ?
        """, (reward, user_id))

        conn.commit()
        conn.close()

        new_balance = get_balance(user_id)

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🎉 VIDEONGIZ TASDIQLANDI!\n\n"
                "✅ Admin videongizni qabul qildi.\n\n"
                f"💰 +{format_money(reward)} balansingizga qo‘shildi.\n"
                f"💳 Joriy balans: {format_money(new_balance)}"
            ),
            reply_markup=main_menu()
        )

        try:
            await query.message.edit_reply_markup(
                reply_markup=None
            )
        except Exception:
            pass

        await query.message.reply_text(
            "✅ VIDEO TASDIQLANDI\n\n"
            f"🆔 Video ID: #{submission_id}\n"
            f"👤 User ID: {user_id}\n"
            f"💰 To‘lov: {format_money(reward)}"
        )

        return

    # =====================================================
    # VIDEO REJECT
    # =====================================================

    if data.startswith("reject:"):

        if user.id != ADMIN_ID:
            return

        try:
            submission_id = int(data.split(":")[1])
        except (ValueError, IndexError):
            return

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            SELECT user_id, status
            FROM submissions
            WHERE id = ?
            AND type = 'video'
        """, (submission_id,))

        row = cur.fetchone()

        if not row:
            conn.close()
            await query.answer(
                "Video topilmadi.",
                show_alert=True
            )
            return

        user_id, status = row

        if status != "pending":
            conn.close()
            await query.answer(
                "Allaqachon ko‘rib chiqilgan.",
                show_alert=True
            )
            return

        cur.execute("""
            UPDATE submissions
            SET status = 'rejected',
                reward = 0
            WHERE id = ?
            AND status = 'pending'
        """, (submission_id,))

        conn.commit()
        conn.close()

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ VIDEONGIZ RAD ETILDI.\n\n"
                "Afsuski, admin videoni tasdiqlamadi.\n"
                "Bu video uchun balansga pul qo‘shilmadi."
            ),
            reply_markup=main_menu()
        )

        try:
            await query.message.edit_reply_markup(
                reply_markup=None
            )
        except Exception:
            pass

        await query.message.reply_text(
            "❌ VIDEO RAD ETILDI\n\n"
            f"🆔 Video ID: #{submission_id}\n"
            f"👤 User ID: {user_id}"
        )

        return

    # =====================================================
    # PAY
    # =====================================================

    if data.startswith("pay:"):

        if user.id != ADMIN_ID:
            return

        try:
            withdrawal_id = int(data.split(":")[1])
        except (ValueError, IndexError):
            return

        conn = db()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT user_id, amount, status
                FROM withdrawals
                WHERE id = ?
            """, (withdrawal_id,))

            row = cur.fetchone()

            if not row:
                await query.answer(
                    "So‘rov topilmadi.",
                    show_alert=True
                )
                return

            user_id, amount, status = row

            if status != "pending":
                await query.answer(
                    "Allaqachon ko‘rib chiqilgan.",
                    show_alert=True
                )
                return

            cur.execute("""
                SELECT balance, reserved_balance
                FROM users
                WHERE id = ?
            """, (user_id,))

            user_row = cur.fetchone()

            if not user_row:
                await query.answer(
                    "Foydalanuvchi topilmadi.",
                    show_alert=True
                )
                return

            balance, reserved = user_row
            reserved = reserved or 0

            if balance < amount or reserved < amount:
                await query.message.reply_text(
                    "❌ Rezerv yoki balans noto‘g‘ri.\n"
                    "To‘lovni amalga oshirib bo‘lmaydi."
                )
                return

            cur.execute("""
                UPDATE users
                SET
                    balance = balance - ?,
                    reserved_balance = reserved_balance - ?
                WHERE id = ?
                AND balance >= ?
                AND reserved_balance >= ?
            """, (
                amount,
                amount,
                user_id,
                amount,
                amount
            ))

            if cur.rowcount != 1:
                conn.rollback()
                await query.message.reply_text(
                    "❌ Balansni yangilab bo‘lmadi."
                )
                return

            cur.execute("""
                UPDATE withdrawals
                SET status = 'paid'
                WHERE id = ?
                AND status = 'pending'
            """, (withdrawal_id,))

            if cur.rowcount != 1:
                conn.rollback()
                await query.message.reply_text(
                    "❌ So‘rov holatini yangilab bo‘lmadi."
                )
                return

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

        new_balance = get_balance(user_id)

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "💸 TO‘LOV AMALGA OSHIRILDI!\n\n"
                f"✅ To‘langan summa: {format_money(amount)}\n"
                f"💰 Qolgan balans: {format_money(new_balance)}"
            ),
            reply_markup=main_menu()
        )

        try:
            await query.message.edit_reply_markup(
                reply_markup=None
            )
        except Exception:
            pass

        await query.message.reply_text(
            "✅ TO‘LANDI\n\n"
            f"👤 User ID: {user_id}\n"
            f"💵 Summa: {format_money(amount)}\n"
            f"💰 Qolgan balans: {format_money(new_balance)}"
        )

        return

    # =====================================================
    # CANCEL PAYMENT
    # =====================================================

    if data.startswith("cancelpay:"):

        if user.id != ADMIN_ID:
            return

        try:
            withdrawal_id = int(data.split(":")[1])
        except (ValueError, IndexError):
            return

        conn = db()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT user_id, amount, status
                FROM withdrawals
                WHERE id = ?
            """, (withdrawal_id,))

            row = cur.fetchone()

            if not row:
                await query.answer(
                    "So‘rov topilmadi.",
                    show_alert=True
                )
                return

            user_id, amount, status = row

            if status != "pending":
                await query.answer(
                    "Allaqachon ko‘rib chiqilgan.",
                    show_alert=True
                )
                return

            cur.execute("""
                UPDATE users
                SET reserved_balance =
                    MAX(0, reserved_balance - ?)
                WHERE id = ?
            """, (amount, user_id))

            cur.execute("""
                UPDATE withdrawals
                SET status = 'rejected'
                WHERE id = ?
                AND status = 'pending'
            """, (withdrawal_id,))

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ PUL YECHISH SO‘ROVI RAD ETILDI.\n\n"
                f"💰 {format_money(amount)} balansingizda qoldi."
            ),
            reply_markup=main_menu()
        )

        try:
            await query.message.edit_reply_markup(
                reply_markup=None
            )
        except Exception:
            pass

        await query.message.reply_text(
            "❌ Pul yechish so‘rovi rad etildi.\n\n"
            "Balansdan pul ayrilmadi."
        )

        return


# =========================================================
# TEXT HANDLER
# =========================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    user = update.effective_user
    mode = context.user_data.get("mode")

    # =====================================================
    # REGISTRATION
    # =====================================================

    if mode == "registration":

        name = update.message.text.strip()

        if len(name) < 2:
            await update.message.reply_text(
                "❌ Ism juda qisqa.\n\n"
                "Iltimos, ismingizni to‘liqroq yozing."
            )
            return

        if len(name) > 100:
            await update.message.reply_text(
                "❌ Ism juda uzun."
            )
            return

        save_user(user, registered_name=name)

        context.user_data.clear()

        username = (
            f"@{user.username}"
            if user.username
            else "Username o‘rnatilmagan"
        )

        await update.message.reply_text(
            "✅ RO‘YXATDAN O‘TDINGIZ!\n\n"
            f"👤 Ism: {name}\n"
            f"🔗 Telegram: {username}\n"
            f"🆔 Telegram ID: {user.id}\n\n"
            "Endi botdan foydalanishingiz mumkin.",
            reply_markup=main_menu()
        )
        return

    # =====================================================
    # APPEAL
    # =====================================================

    if mode == "appeal":

        text = update.message.text.strip()

        if not text:
            await update.message.reply_text(
                "❌ Murojaat bo‘sh bo‘lishi mumkin emas."
            )
            return

        if len(text) > 4000:
            await update.message.reply_text(
                "❌ Murojaat 4000 belgidan oshmasin."
            )
            return

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO submissions
            (user_id, type, content, status, reward)
            VALUES (?, 'appeal', ?, 'pending', 0)
        """, (user.id, text))

        submission_id = cur.lastrowid

        conn.commit()
        conn.close()

        user_data = get_user(user.id)

        registered_name = (
            user_data[4]
            if user_data
            else "—"
        )

        username = (
            f"@{user.username}"
            if user.username
            else "Username yo‘q"
        )

        admin_text = (
            "✉️ YANGI MUROJAAT\n\n"
            f"🆔 Murojaat ID: #{submission_id}\n\n"
            f"👤 Ism: {registered_name}\n"
            f"🔗 Username: {username}\n"
            f"🆔 Telegram ID: {user.id}\n\n"
            "📝 MUROJAAT:\n\n"
            f"{text}\n\n"
            "💰 To‘lov: 0 so‘m"
        )

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=appeal_menu(submission_id)
        )

        await update.message.reply_text(
            "✅ Murojaatingiz adminlarga yuborildi.\n\n"
            "📩 Adminlar ko‘rib chiqadi.\n\n"
            "⚠️ Oddiy murojaatlar uchun pul to‘lanmaydi.",
            reply_markup=main_menu()
        )

        context.user_data.clear()
        return

    # =====================================================
    # WITHDRAW AMOUNT
    # =====================================================

    if mode == "withdraw_amount":

        try:
            amount = int(
                update.message.text.replace(" ", "")
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Summani raqam bilan kiriting.\n\n"
                "Masalan: 15000"
            )
            return

        if amount < MIN_WITHDRAW:
            await update.message.reply_text(
                f"❌ Minimal summa: {format_money(MIN_WITHDRAW)}"
            )
            return

        available = get_available_balance(user.id)

        if amount > available:
            await update.message.reply_text(
                "❌ Balansingiz yetarli emas.\n\n"
                f"💰 Mavjud: {format_money(available)}\n"
                f"💸 So‘ralgan: {format_money(amount)}"
            )
            return

        context.user_data["withdraw_amount"] = amount
        context.user_data["mode"] = "withdraw_card"

        await update.message.reply_text(
            "💳 BANK KARTA RAQAMINI KIRITING\n\n"
            "16 xonali plastik karta raqamini yuboring.\n\n"
            "Masalan:\n"
            "8600 1234 5678 9012\n\n"
            "⚠️ CVV, PIN yoki SMS kod yubormang."
        )
        return

    # =====================================================
    # WITHDRAW CARD
    # =====================================================

    if mode == "withdraw_card":

        card = normalize_card(
            update.message.text.strip()
        )

        if not card:
            await update.message.reply_text(
                "❌ Karta raqami noto‘g‘ri.\n\n"
                "16 xonali karta raqamini kiriting.\n\n"
                "Masalan:\n"
                "8600 1234 5678 9012"
            )
            return

        amount = context.user_data.get(
            "withdraw_amount"
        )

        if not amount:
            context.user_data.clear()

            await update.message.reply_text(
                "❌ So‘rov bekor qilindi.",
                reply_markup=main_menu()
            )
            return

        conn = db()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT balance, reserved_balance
                FROM users
                WHERE id = ?
            """, (user.id,))

            row = cur.fetchone()

            if not row:
                conn.rollback()
                await update.message.reply_text(
                    "❌ Foydalanuvchi topilmadi."
                )
                return

            balance, reserved = row
            reserved = reserved or 0

            available = balance - reserved

            if amount > available:
                conn.rollback()

                await update.message.reply_text(
                    "❌ Balansingiz yetarli emas."
                )
                return

            # Balansni yechmaymiz.
            # Faqat vaqtincha rezerv qilamiz.
            cur.execute("""
                UPDATE users
                SET reserved_balance =
                    reserved_balance + ?
                WHERE id = ?
            """, (amount, user.id))

            cur.execute("""
                INSERT INTO withdrawals
                (
                    user_id,
                    amount,
                    card_number,
                    status
                )
                VALUES (?, ?, ?, 'pending')
            """, (
                user.id,
                amount,
                card
            ))

            withdrawal_id = cur.lastrowid

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

        user_data = get_user(user.id)

        registered_name = (
            user_data[4]
            if user_data
            else "—"
        )

        username = (
            f"@{user.username}"
            if user.username
            else "Username yo‘q"
        )

        admin_text = (
            "💳 YANGI PUL YECHISH SO‘ROVI\n\n"
            f"🆔 So‘rov ID: #{withdrawal_id}\n\n"
            f"👤 Ism: {registered_name}\n"
            f"🔗 Username: {username}\n"
            f"🆔 Telegram ID: {user.id}\n\n"
            f"💰 Summa: {format_money(amount)}\n"
            f"💳 Karta: {card}\n\n"
            "⚠️ Summa vaqtincha rezerv qilindi."
        )

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=withdrawal_menu(
                withdrawal_id
            )
        )

        await update.message.reply_text(
            "✅ PUL YECHISH SO‘ROVI YUBORILDI!\n\n"
            f"💵 Summa: {format_money(amount)}\n"
            f"💳 Karta: {card}\n\n"
            "Admin to‘lovni amalga oshirgach, "
            "summa balansdan yechiladi.",
            reply_markup=main_menu()
        )

        context.user_data.clear()
        return

    # =====================================================
    # ADMIN REPLY
    # =====================================================

    if mode == "admin_reply":

        if user.id != ADMIN_ID:
            return

        reply_text = update.message.text.strip()

        if not reply_text:
            await update.message.reply_text(
                "❌ Javob bo‘sh bo‘lishi mumkin emas."
            )
            return

        submission_id = context.user_data.get(
            "reply_submission_id"
        )

        if not submission_id:
            context.user_data.clear()
            return

        conn = db()
        cur = conn.cursor()

        cur.execute("""
            SELECT user_id
            FROM submissions
            WHERE id = ?
            AND type = 'appeal'
        """, (submission_id,))

        row = cur.fetchone()

        if not row:
            conn.close()
            context.user_data.clear()

            await update.message.reply_text(
                "❌ Murojaat topilmadi."
            )
            return

        user_id = row[0]

        cur.execute("""
            UPDATE submissions
            SET status = 'answered'
            WHERE id = ?
        """, (submission_id,))

        conn.commit()
        conn.close()

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "💬 MUROJAATINGIZGA JAVOB\n\n"
                f"{reply_text}\n\n"
                f"🆔 Murojaat: #{submission_id}"
            ),
            reply_markup=main_menu()
        )

        await update.message.reply_text(
            "✅ Javob foydalanuvchiga yuborildi."
        )

        context.user_data.clear()
        return

    # =====================================================
    # DEFAULT
    # =====================================================

    await update.message.reply_text(
        "👇 Kerakli bo‘limni tanlang:",
        reply_markup=main_menu()
    )


# =========================================================
# VIDEO HANDLER
# =========================================================

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message:
        return

    user = update.effective_user
    mode = context.user_data.get("mode")

    if mode != "video":
        return

    user_data = get_user(user.id)

    if not user_data:
        await update.message.reply_text(
            "❌ Avval /start orqali ro‘yxatdan o‘ting."
        )
        return

    registered_name = user_data[4]

    username = (
        f"@{user.username}"
        if user.username
        else "Username yo‘q"
    )

    file_id = None

    if update.message.video:
        file_id = update.message.video.file_id

    elif update.message.document:

        mime = (
            update.message.document.mime_type
            or ""
        )

        if not mime.startswith("video/"):
            await update.message.reply_text(
                "❌ Faqat video fayl yuboring."
            )
            return

        file_id = update.message.document.file_id

    if not file_id:
        await update.message.reply_text(
            "❌ Iltimos, video yuboring."
        )
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO submissions
        (
            user_id,
            type,
            content,
            status,
            reward
        )
        VALUES (?, 'video', ?, 'pending', 0)
    """, (
        user.id,
        file_id
    ))

    submission_id = cur.lastrowid

    conn.commit()
    conn.close()

    caption = (
        "🎥 YANGI VIDEO\n\n"
        f"🆔 Video ID: #{submission_id}\n\n"
        f"👤 Ism: {registered_name}\n"
        f"🔗 Username: {username}\n"
        f"🆔 Telegram ID: {user.id}\n\n"
        "💰 To‘lov: 5 000 – 15 000 so‘m\n\n"
        "Admin videoni ko‘rib, to‘lov miqdorini tanlaydi."
    )

    keyboard = video_reward_menu(
        submission_id
    )

    if update.message.video:
        await context.bot.send_video(
            chat_id=ADMIN_ID,
            video=file_id,
            caption=caption,
            reply_markup=keyboard
        )
    else:
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=file_id,
            caption=caption,
            reply_markup=keyboard
        )

    await update.message.reply_text(
        "✅ VIDEONGIZ QABUL QILINDI!\n\n"
        "🎥 Video adminlarga yuborildi.\n\n"
        "💰 Admin videoni baholaydi:\n"
        "5 000 – 15 000 so‘m\n\n"
        "Tasdiqlangandan keyin pul balansingizga qo‘shiladi.",
        reply_markup=main_menu()
    )

    context.user_data.clear()


# =========================================================
# ADMIN COMMAND
# =========================================================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Siz admin emassiz."
        )
        return

    await update.message.reply_text(
        "👨‍💼 ADMIN PANEL",
        reply_markup=admin_menu()
    )


# =========================================================
# USERS COMMAND
# =========================================================

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            username,
            registered_name,
            balance,
            reserved_balance
        FROM users
        ORDER BY balance DESC
    """)

    users = cur.fetchall()
    conn.close()

    if not users:
        await update.message.reply_text(
            "👥 Foydalanuvchilar yo‘q."
        )
        return

    text = "👥 FOYDALANUVCHILAR\n\n"

    for user_id, username, name, balance, reserved in users:

        username_text = (
            f"@{username}"
            if username
            else "Username yo‘q"
        )

        text += (
            f"👤 {name or 'Ism kiritilmagan'}\n"
            f"🔗 {username_text}\n"
            f"🆔 {user_id}\n"
            f"💰 Balans: {format_money(balance)}\n"
            f"⏳ Rezerv: {format_money(reserved or 0)}\n"
            "──────────────\n"
        )

    await update.message.reply_text(text)


# =========================================================
# WITHDRAWALS COMMAND
# =========================================================

async def withdrawals_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            user_id,
            amount,
            card_number,
            status
        FROM withdrawals
        ORDER BY id DESC
        LIMIT 30
    """)

    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(
            "💳 Pul yechish so‘rovlari yo‘q."
        )
        return

    for withdrawal_id, user_id, amount, card, status in rows:

        status_text = {
            "pending": "⏳ Kutilmoqda",
            "paid": "✅ To‘langan",
            "rejected": "❌ Rad etilgan",
        }.get(status, status)

        text = (
            "💳 PUL YECHISH SO‘ROVI\n\n"
            f"🆔 #{withdrawal_id}\n"
            f"👤 User: {user_id}\n"
            f"💰 {format_money(amount)}\n"
            f"💳 Karta: {card or '—'}\n"
            f"📌 {status_text}"
        )

        keyboard = (
            withdrawal_menu(withdrawal_id)
            if status == "pending"
            else None
        )

        await update.message.reply_text(
            text,
            reply_markup=keyboard
        )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Botda xatolik:",
        exc_info=context.error
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN topilmadi.\n\n"
            "PowerShell:\n"
            '$env:BOT_TOKEN="YANGI_TOKEN"\n\n'
            "Keyin:\n"
            "python bot.py"
        )

    init_db()

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # COMMANDS
    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("admin", admin)
    )

    app.add_handler(
        CommandHandler("users", users_command)
    )

    app.add_handler(
        CommandHandler(
            "withdrawals",
            withdrawals_command
        )
    )

    # CALLBACKS
    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    # VIDEO
    app.add_handler(
        MessageHandler(
            filters.VIDEO,
            handle_video
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_video
        )
    )

    # TEXT
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    # ERROR
    app.add_error_handler(
        error_handler
    )

    print(
        "🚀 Navoiyliklar.uz bot ishga tushdi..."
    )

    app.run_polling()




if __name__ == "__main__":
    main()