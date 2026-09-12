import os
import re
import logging
import psycopg2

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
DATABASE_URL = os.getenv("DATABASE_URL")

ADMIN_ID = 7267416938

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
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL topilmadi.")

    return psycopg2.connect(DATABASE_URL)


def init_db():
    conn = db()
    cur = conn.cursor()

    try:
        # USERS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT DEFAULT '',
                full_name TEXT DEFAULT '',
                balance BIGINT DEFAULT 0,
                registered_name TEXT DEFAULT '',
                reserved_balance BIGINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # SUBMISSIONS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                type TEXT NOT NULL,
                content TEXT,
                status TEXT DEFAULT 'pending',
                reward BIGINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # WITHDRAWALS
        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount BIGINT NOT NULL,
                card_number TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Eski DB bo'lsa ham ishlashi uchun
        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS registered_name TEXT DEFAULT ''
        """)

        cur.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS reserved_balance BIGINT DEFAULT 0
        """)

        cur.execute("""
            ALTER TABLE withdrawals
            ADD COLUMN IF NOT EXISTS card_number TEXT
        """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


# =========================================================
# USER FUNKSIYALAR
# =========================================================

def save_user(user_id, username="", full_name=""):
    conn = db()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO users (
                id,
                username,
                full_name
            )
            VALUES (%s, %s, %s)

            ON CONFLICT (id)
            DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name
        """, (
            user_id,
            username or "",
            full_name or "",
        ))

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


def get_user(user_id):
    conn = db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                id,
                username,
                full_name,
                balance,
                registered_name,
                reserved_balance
            FROM users
            WHERE id = %s
        """, (user_id,))

        return cur.fetchone()

    finally:
        cur.close()
        conn.close()


def get_balance(user_id):
    user = get_user(user_id)

    if not user:
        return 0

    return user[3] or 0


def get_reserved_balance(user_id):
    user = get_user(user_id)

    if not user:
        return 0

    return user[5] or 0


def get_available_balance(user_id):
    balance = get_balance(user_id)
    reserved = get_reserved_balance(user_id)

    return max(0, balance - reserved)


def format_money(amount):
    return f"{amount:,}".replace(",", " ") + " so'm"


def normalize_card(card):
    return re.sub(r"\D", "", card or "")


def mask_card(card):
    card = normalize_card(card)

    if len(card) < 8:
        return card

    return f"{card[:4]} **** **** {card[-4:]}"


# =========================================================
# MENYULAR
# =========================================================

def main_menu():
    keyboard = [
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
            )
        ],
        [
            InlineKeyboardButton(
                "💳 Pul yechish",
                callback_data="withdraw"
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def admin_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "🎥 Videolar",
                callback_data="admin_videos"
            )
        ],
        [
            InlineKeyboardButton(
                "✉️ Murojaatlar",
                callback_data="admin_appeals"
            )
        ],
        [
            InlineKeyboardButton(
                "💳 Pul yechish",
                callback_data="admin_withdrawals"
            )
        ],
        [
            InlineKeyboardButton(
                "👥 Foydalanuvchilar",
                callback_data="admin_users"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Statistika",
                callback_data="admin_stats"
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# VIDEO REWARD MENU
# =========================================================

def video_reward_menu(submission_id):
    keyboard = [
        [
            InlineKeyboardButton(
                "5 000 so'm",
                callback_data=f"reward:{submission_id}:5000"
            ),
            InlineKeyboardButton(
                "7 500 so'm",
                callback_data=f"reward:{submission_id}:7500"
            ),
        ],
        [
            InlineKeyboardButton(
                "10 000 so'm",
                callback_data=f"reward:{submission_id}:10000"
            ),
            InlineKeyboardButton(
                "12 500 so'm",
                callback_data=f"reward:{submission_id}:12500"
            ),
        ],
        [
            InlineKeyboardButton(
                "15 000 so'm",
                callback_data=f"reward:{submission_id}:15000"
            ),
        ],
        [
            InlineKeyboardButton(
                "❌ Rad etish",
                callback_data=f"reject:{submission_id}"
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# WITHDRAWAL MENU
# =========================================================

def withdrawal_menu(withdrawal_id):
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ To'landi",
                callback_data=f"paid:{withdrawal_id}"
            ),
            InlineKeyboardButton(
                "❌ Rad etish",
                callback_data=f"cancelpay:{withdrawal_id}"
            ),
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# APPEAL REPLY MENU
# =========================================================

def appeal_menu(submission_id):
    keyboard = [
        [
            InlineKeyboardButton(
                "💬 Javob berish",
                callback_data=f"reply:{submission_id}"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# /START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    save_user(
        user.id,
        user.username or "",
        user.full_name or "",
    )

    existing = get_user(user.id)

    if not existing or not existing[4]:

        context.user_data["mode"] = "registration"

        await update.message.reply_text(
            "👋 Assalomu alaykum!\n\n"
            "📰 Navoiyliklar.uz botiga xush kelibsiz.\n\n"
            "Botdan foydalanish uchun avval ro‘yxatdan o‘ting.\n\n"
            "👤 Ismingizni yozing:"
        )

        return

    context.user_data.pop("mode", None)

    await update.message.reply_text(
        "👋 Assalomu alaykum!\n\n"
        "📰 Navoiyliklar.uz botiga xush kelibsiz!\n\n"
        "Bu bot orqali siz:\n\n"
        "✉️ Yangilik, taklif yoki murojaat yuborishingiz\n"
        "🎥 Eksklyuziv videolaringizni sotishingiz\n"
        "💰 Video uchun yig‘ilgan balansingizni ko‘rishingiz\n"
        "💳 Mablag‘ingizni plastik kartangizga yechishingiz mumkin.\n\n"
        "Quyidagi menyudan kerakli bo‘limni tanlang 👇",
        reply_markup=main_menu()
    )


# =========================================================
# ADMIN
# =========================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Sizda admin huquqi yo‘q."
        )
        return

    await update.message.reply_text(
        "🛠 Admin panel",
        reply_markup=admin_menu()
    )


# =========================================================
# BUTTON HANDLER
# =========================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    # =====================================================
    # ODDIY MUROJAAT
    # =====================================================

    if data == "appeal":

        context.user_data["mode"] = "appeal"

        await query.message.reply_text(
            "✉️ Oddiy murojaat\n\n"
            "Savol, taklif, shikoyat yoki voqea haqida "
            "ma'lumot yuborishingiz mumkin.\n\n"
            "Xabaringizni yozing:"
        )

        return

    # =====================================================
    # VIDEO
    # =====================================================

    if data == "video":

        context.user_data["mode"] = "video"

        await query.message.reply_text(
            "🎥 Video sotaman\n\n"
            "O'zingiz suratga olgan yoki eksklyuziv "
            "video yuboring.\n\n"
            "📌 Video qiymati admin tomonidan "
            "5 000 – 15 000 so'm oralig'ida belgilanadi.\n\n"
            "Videoni yuboring:"
        )

        return

    # =====================================================
    # BALANCE
    # =====================================================

    if data == "balance":

        balance = get_balance(user_id)
        reserved = get_reserved_balance(user_id)
        available = get_available_balance(user_id)

        await query.message.reply_text(
            "💰 Balansingiz\n\n"
            f"Jami: {format_money(balance)}\n"
            f"Band qilingan: {format_money(reserved)}\n"
            f"Yechish mumkin: {format_money(available)}"
        )

        return

    # =====================================================
    # WITHDRAW
    # =====================================================

    if data == "withdraw":

        available = get_available_balance(user_id)

        if available < MIN_WITHDRAW:

            await query.message.reply_text(
                "❌ Pul yechish uchun balansingizda kamida "
                f"{format_money(MIN_WITHDRAW)} bo‘lishi kerak.\n\n"
                f"Sizning mavjud balansingiz: "
                f"{format_money(available)}"
            )

            return

        context.user_data["mode"] = "withdraw_amount"

        await query.message.reply_text(
            "💳 Pul yechish\n\n"
            f"Minimal summa: {format_money(MIN_WITHDRAW)}\n"
            f"Mavjud balans: {format_money(available)}\n\n"
            "Qancha pul yechmoqchisiz?\n\n"
            "Masalan: 10000"
        )

        return

    # =====================================================
    # ADMIN PANEL
    # =====================================================

    if user_id != ADMIN_ID:
        return

    # =====================================================
    # ADMIN VIDEOS
    # =====================================================

    if data == "admin_videos":

        conn = db()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT
                    s.id,
                    s.user_id,
                    s.status,
                    s.reward,
                    s.created_at,
                    u.registered_name,
                    u.username
                FROM submissions s
                LEFT JOIN users u
                    ON u.id = s.user_id
                WHERE s.type = 'video'
                ORDER BY s.id DESC
                LIMIT 20
            """)

            rows = cur.fetchall()

        finally:
            cur.close()
            conn.close()

        if not rows:

            await query.message.reply_text(
                "🎥 Videolar yo‘q."
            )

            return

        for row in rows:

            submission_id = row[0]
            tg_id = row[1]
            status = row[2]
            reward = row[3]
            created_at = row[4]
            name = row[5] or "Noma'lum"
            username = row[6] or "-"

            text = (
                f"🎥 Video #{submission_id}\n\n"
                f"👤 Ism: {name}\n"
                f"🔗 Username: @{username if username != '-' else '-'}\n"
                f"🆔 Telegram ID: {tg_id}\n"
                f"📌 Status: {status}\n"
                f"💰 Mukofot: {format_money(reward)}\n"
                f"🕐 {created_at}"
            )

            await query.message.reply_text(text)

        return

    # =====================================================
    # ADMIN APPEALS
    # =====================================================

    if data == "admin_appeals":

        conn = db()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT
                    s.id,
                    s.user_id,
                    s.content,
                    s.status,
                    s.created_at,
                    u.registered_name,
                    u.username
                FROM submissions s
                LEFT JOIN users u
                    ON u.id = s.user_id
                WHERE s.type = 'appeal'
                ORDER BY s.id DESC
                LIMIT 20
            """)

            rows = cur.fetchall()

        finally:
            cur.close()
            conn.close()

        if not rows:

            await query.message.reply_text(
                "✉️ Murojaatlar yo‘q."
            )

            return

        for row in rows:

            submission_id = row[0]
            tg_id = row[1]
            content = row[2] or ""
            status = row[3]
            created_at = row[4]
            name = row[5] or "Noma'lum"
            username = row[6] or "-"

            text = (
                f"✉️ Murojaat #{submission_id}\n\n"
                f"👤 Ism: {name}\n"
                f"🔗 Username: @{username if username != '-' else '-'}\n"
                f"🆔 Telegram ID: {tg_id}\n"
                f"📌 Status: {status}\n"
                f"🕐 {created_at}\n\n"
                f"📝 Murojaat:\n{content}"
            )

            keyboard = None

            if status == "pending":

                keyboard = appeal_menu(submission_id)

            await query.message.reply_text(
                text,
                reply_markup=keyboard
            )

        return

    # =====================================================
    # ADMIN WITHDRAWALS
    # =====================================================

    if data == "admin_withdrawals":

        conn = db()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT
                    w.id,
                    w.user_id,
                    w.amount,
                    w.card_number,
                    w.status,
                    w.created_at,
                    u.registered_name,
                    u.username
                FROM withdrawals w
                LEFT JOIN users u
                    ON u.id = w.user_id
                ORDER BY w.id DESC
                LIMIT 20
            """)

            rows = cur.fetchall()

        finally:
            cur.close()
            conn.close()

        if not rows:

            await query.message.reply_text(
                "💳 Pul yechish so‘rovlari yo‘q."
            )

            return

        for row in rows:

            withdrawal_id = row[0]
            tg_id = row[1]
            amount = row[2]
            card = row[3] or ""
            status = row[4]
            created_at = row[5]
            name = row[6] or "Noma'lum"
            username = row[7] or "-"

            text = (
                f"💳 Pul yechish #{withdrawal_id}\n\n"
                f"👤 Ism: {name}\n"
                f"🔗 Username: @{username if username != '-' else '-'}\n"
                f"🆔 Telegram ID: {tg_id}\n"
                f"💰 Summa: {format_money(amount)}\n"
                f"💳 Karta: {card}\n"
                f"📌 Status: {status}\n"
                f"🕐 {created_at}"
            )

            keyboard = None

            if status == "pending":

                keyboard = withdrawal_menu(
                    withdrawal_id
                )

            await query.message.reply_text(
                text,
                reply_markup=keyboard
            )

        return

    # =====================================================
    # ADMIN USERS
    # =====================================================

    if data == "admin_users":

        conn = db()
        cur = conn.cursor()

        try:
            cur.execute("""
                SELECT
                    id,
                    registered_name,
                    username,
                    balance,
                    reserved_balance,
                    created_at
                FROM users
                ORDER BY id DESC
                LIMIT 30
            """)

            rows = cur.fetchall()

        finally:
            cur.close()
            conn.close()

        if not rows:

            await query.message.reply_text(
                "👥 Foydalanuvchilar yo‘q."
            )

            return

        for row in rows:

            tg_id = row[0]
            name = row[1] or "Noma'lum"
            username = row[2] or "-"
            balance = row[3] or 0
            reserved = row[4] or 0
            created_at = row[5]

            await query.message.reply_text(
                "👤 Foydalanuvchi\n\n"
                f"Ism: {name}\n"
                f"Username: @{username if username != '-' else '-'}\n"
                f"Telegram ID: {tg_id}\n"
                f"Balans: {format_money(balance)}\n"
                f"Band: {format_money(reserved)}\n"
                f"Ro‘yxatdan o‘tgan: {created_at}"
            )

        return

    # =====================================================
    # ADMIN STATISTICS
    # =====================================================

    if data == "admin_stats":

        conn = db()
        cur = conn.cursor()

        try:
            cur.execute(
                "SELECT COUNT(*) FROM users"
            )
            users_count = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*)
                FROM submissions
                WHERE type = 'video'
            """)
            videos_count = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*)
                FROM submissions
                WHERE type = 'appeal'
            """)
            appeals_count = cur.fetchone()[0]

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

        finally:
            cur.close()
            conn.close()

        await query.message.reply_text(
            "📊 Statistika\n\n"
            f"👥 Foydalanuvchilar: {users_count}\n"
            f"🎥 Videolar: {videos_count}\n"
            f"✉️ Murojaatlar: {appeals_count}\n"
            f"💳 Kutilayotgan yechishlar: {pending_withdrawals}\n"
            f"💰 Jami balanslar: {format_money(total_balance)}"
        )

        return

    # =====================================================
    # VIDEO REWARD
    # =====================================================

    if data.startswith("reward:"):

        parts = data.split(":")

        submission_id = int(parts[1])
        reward = int(parts[2])

        if not (
            MIN_VIDEO_REWARD
            <= reward
            <= MAX_VIDEO_REWARD
        ):

            await query.message.reply_text(
                "❌ Noto‘g‘ri mukofot."
            )

            return

        conn = db()
        cur = conn.cursor()

        try:

            cur.execute("""
                SELECT
                    user_id,
                    status
                FROM submissions
                WHERE id = %s
                AND type = 'video'
                FOR UPDATE
            """, (submission_id,))

            submission = cur.fetchone()

            if not submission:

                await query.message.reply_text(
                    "❌ Video topilmadi."
                )

                return

            target_user_id = submission[0]
            status = submission[1]

            if status != "pending":

                await query.message.reply_text(
                    "⚠️ Bu video allaqachon ko‘rib chiqilgan."
                )

                return

            cur.execute("""
                UPDATE submissions
                SET
                    status = 'approved',
                    reward = %s
                WHERE id = %s
            """, (
                reward,
                submission_id,
            ))

            cur.execute("""
                UPDATE users
                SET balance = balance + %s
                WHERE id = %s
            """, (
                reward,
                target_user_id,
            ))

            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            cur.close()
            conn.close()

        try:

            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "🎉 Videongiz qabul qilindi!\n\n"
                    f"💰 Sizga {format_money(reward)} "
                    "to‘lov belgilandi.\n\n"
                    "Balansingiz yangilandi."
                )
            )

        except Exception as e:

            logger.error(
                f"Userga xabar yuborilmadi: {e}"
            )

        await query.message.edit_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            f"✅ Video #{submission_id} tasdiqlandi.\n"
            f"💰 Mukofot: {format_money(reward)}"
        )

        return

    # =====================================================
    # VIDEO REJECT
    # =====================================================

    if data.startswith("reject:"):

        submission_id = int(
            data.split(":")[1]
        )

        conn = db()
        cur = conn.cursor()

        try:

            cur.execute("""
                SELECT
                    user_id,
                    status
                FROM submissions
                WHERE id = %s
                AND type = 'video'
                FOR UPDATE
            """, (submission_id,))

            submission = cur.fetchone()

            if not submission:

                await query.message.reply_text(
                    "❌ Video topilmadi."
                )

                return

            target_user_id = submission[0]
            status = submission[1]

            if status != "pending":

                await query.message.reply_text(
                    "⚠️ Bu video allaqachon ko‘rib chiqilgan."
                )

                return

            cur.execute("""
                UPDATE submissions
                SET status = 'rejected'
                WHERE id = %s
            """, (submission_id,))

            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            cur.close()
            conn.close()

        try:

            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "❌ Afsuski, yuborgan videongiz "
                    "qabul qilinmadi."
                )
            )

        except Exception as e:

            logger.error(
                f"Userga reject xabari yuborilmadi: {e}"
            )

        await query.message.edit_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            f"❌ Video #{submission_id} rad etildi."
        )

        return

    # =====================================================
    # APPEAL REPLY
    # =====================================================

    if data.startswith("reply:"):

        submission_id = int(
            data.split(":")[1]
        )

        conn = db()
        cur = conn.cursor()

        try:

            cur.execute("""
                SELECT
                    user_id,
                    status
                FROM submissions
                WHERE id = %s
                AND type = 'appeal'
            """, (submission_id,))

            submission = cur.fetchone()

        finally:

            cur.close()
            conn.close()

        if not submission:

            await query.message.reply_text(
                "❌ Murojaat topilmadi."
            )

            return

        if submission[1] != "pending":

            await query.message.reply_text(
                "⚠️ Bu murojaatga allaqachon javob berilgan."
            )

            return

        context.user_data["mode"] = "admin_reply"
        context.user_data["reply_submission_id"] = submission_id
        context.user_data["reply_user_id"] = submission[0]

        await query.message.reply_text(
            f"💬 Murojaat #{submission_id} uchun javobni yozing:"
        )

        return

    # =====================================================
    # WITHDRAWAL PAID
    # =====================================================

    if data.startswith("paid:"):

        withdrawal_id = int(
            data.split(":")[1]
        )

        conn = db()
        cur = conn.cursor()

        try:

            cur.execute("""
                SELECT
                    user_id,
                    amount,
                    status
                FROM withdrawals
                WHERE id = %s
                FOR UPDATE
            """, (withdrawal_id,))

            withdrawal = cur.fetchone()

            if not withdrawal:

                await query.message.reply_text(
                    "❌ So‘rov topilmadi."
                )

                return

            target_user_id = withdrawal[0]
            amount = withdrawal[1]
            status = withdrawal[2]

            if status != "pending":

                await query.message.reply_text(
                    "⚠️ Bu so‘rov allaqachon ko‘rib chiqilgan."
                )

                return

            cur.execute("""
                SELECT balance, reserved_balance
                FROM users
                WHERE id = %s
                FOR UPDATE
            """, (target_user_id,))

            user = cur.fetchone()

            if not user:

                await query.message.reply_text(
                    "❌ Foydalanuvchi topilmadi."
                )

                return

            balance = user[0]
            reserved = user[1]

            if balance < amount:

                await query.message.reply_text(
                    "❌ Foydalanuvchi balansida yetarli "
                    "mablag‘ yo‘q."
                )

                return

            cur.execute("""
                UPDATE users
                SET
                    balance = balance - %s,
                    reserved_balance =
                        GREATEST(0, reserved_balance - %s)
                WHERE id = %s
            """, (
                amount,
                amount,
                target_user_id,
            ))

            cur.execute("""
                UPDATE withdrawals
                SET status = 'paid'
                WHERE id = %s
            """, (withdrawal_id,))

            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            cur.close()
            conn.close()

        try:

            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "✅ Pul yechish so‘rovingiz "
                    "tasdiqlandi.\n\n"
                    f"💰 To‘lov: {format_money(amount)}"
                )
            )

        except Exception as e:

            logger.error(
                f"Payment xabari yuborilmadi: {e}"
            )

        await query.message.edit_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            f"✅ Pul yechish #{withdrawal_id} "
            f"to‘landi."
        )

        return

    # =====================================================
    # WITHDRAWAL CANCEL
    # =====================================================

    if data.startswith("cancelpay:"):

        withdrawal_id = int(
            data.split(":")[1]
        )

        conn = db()
        cur = conn.cursor()

        try:

            cur.execute("""
                SELECT
                    user_id,
                    amount,
                    status
                FROM withdrawals
                WHERE id = %s
                FOR UPDATE
            """, (withdrawal_id,))

            withdrawal = cur.fetchone()

            if not withdrawal:

                await query.message.reply_text(
                    "❌ So‘rov topilmadi."
                )

                return

            target_user_id = withdrawal[0]
            amount = withdrawal[1]
            status = withdrawal[2]

            if status != "pending":

                await query.message.reply_text(
                    "⚠️ Bu so‘rov allaqachon ko‘rib chiqilgan."
                )

                return

            cur.execute("""
                UPDATE users
                SET reserved_balance =
                    GREATEST(
                        0,
                        reserved_balance - %s
                    )
                WHERE id = %s
            """, (
                amount,
                target_user_id,
            ))

            cur.execute("""
                UPDATE withdrawals
                SET status = 'rejected'
                WHERE id = %s
            """, (withdrawal_id,))

            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            cur.close()
            conn.close()

        try:

            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "❌ Pul yechish so‘rovingiz "
                    "rad etildi.\n\n"
                    "Mablag‘ingiz balansingizda qoldirildi."
                )
            )

        except Exception as e:

            logger.error(
                f"Reject payment xabari yuborilmadi: {e}"
            )

        await query.message.edit_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            f"❌ Pul yechish #{withdrawal_id} rad etildi."
        )

        return


# =========================================================
# TEXT MESSAGE HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user
    text = (update.message.text or "").strip()

    user_id = user.id

    save_user(
        user_id,
        user.username or "",
        user.full_name or "",
    )

    mode = context.user_data.get("mode")

    # =====================================================
    # REGISTRATION
    # =====================================================

    if mode == "registration":

        if len(text) < 2:

            await update.message.reply_text(
                "❌ Iltimos, ismingizni to‘liqroq yozing."
            )

            return

        conn = db()
        cur = conn.cursor()

        try:

            cur.execute("""
                UPDATE users
                SET registered_name = %s
                WHERE id = %s
            """, (
                text,
                user_id,
            ))

            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            cur.close()
            conn.close()

        context.user_data.pop("mode", None)

        await update.message.reply_text(
            "✅ Ro‘yxatdan o‘tish muvaffaqiyatli yakunlandi!\n\n"
            f"👤 Ism: {text}\n"
            f"🔗 Telegram: "
            f"@{user.username if user.username else '-'}\n"
            f"🆔 Telegram ID: {user_id}\n\n"
            "📰 Navoiyliklar.uz botidan foydalanishingiz mumkin.",
            reply_markup=main_menu()
        )

        return

    # =====================================================
    # APPEAL
    # =====================================================

    if mode == "appeal":

        if not text:

            await update.message.reply_text(
                "❌ Murojaat matni bo‘sh bo‘lmasligi kerak."
            )

            return

        conn = db()
        cur = conn.cursor()

        try:

            cur.execute("""
                INSERT INTO submissions (
                    user_id,
                    type,
                    content,
                    status
                )
                VALUES (
                    %s,
                    'appeal',
                    %s,
                    'pending'
                )
                RETURNING id
            """, (
                user_id,
                text,
            ))

            submission_id = cur.fetchone()[0]

            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            cur.close()
            conn.close()

        context.user_data.pop("mode", None)

        user_name = get_user(user_id)

        registered_name = (
            user_name[4]
            if user_name and user_name[4]
            else "Noma'lum"
        )

        username = user.username or "-"

        admin_text = (
            f"✉️ Yangi murojaat #{submission_id}\n\n"
            f"👤 Ism: {registered_name}\n"
            f"🔗 Username: "
            f"@{username if username != '-' else '-'}\n"
            f"🆔 Telegram ID: {user_id}\n\n"
            f"📝 Murojaat:\n{text}"
        )

        try:

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                reply_markup=appeal_menu(
                    submission_id
                )
            )

        except Exception as e:

            logger.error(
                f"Admin xabari yuborilmadi: {e}"
            )

        await update.message.reply_text(
            "✅ Murojaatingiz qabul qilindi.\n\n"
            "Adminlarimiz ko‘rib chiqadi va "
            "zarur bo‘lsa siz bilan bog‘lanadi.",
            reply_markup=main_menu()
        )

        return

    # =====================================================
    # WITHDRAW AMOUNT
    # =====================================================

    if mode == "withdraw_amount":

        amount_text = re.sub(r"[^\d]", "", text)

        if not amount_text:

            await update.message.reply_text(
                "❌ Faqat summa kiriting.\n\n"
                "Masalan: 10000"
            )

            return

        amount = int(amount_text)

        available = get_available_balance(user_id)

        if amount < MIN_WITHDRAW:

            await update.message.reply_text(
                f"❌ Minimal yechish summasi "
                f"{format_money(MIN_WITHDRAW)}."
            )

            return

        if amount > available:

            await update.message.reply_text(
                "❌ Balansingizda yetarli mablag‘ yo‘q.\n\n"
                f"Mavjud: {format_money(available)}"
            )

            return

        context.user_data["withdraw_amount"] = amount
        context.user_data["mode"] = "withdraw_card"

        await update.message.reply_text(
            "💳 Endi 16 xonali bank karta raqamingizni yuboring.\n\n"
            "Masalan:\n"
            "8600 1234 5678 9012"
        )

        return

    # =====================================================
    # WITHDRAW CARD
    # =====================================================

    if mode == "withdraw_card":

        card = normalize_card(text)

        if len(card) != 16:

            await update.message.reply_text(
                "❌ Karta raqami 16 xonadan iborat bo‘lishi kerak.\n\n"
                "Masalan:\n"
                "8600 1234 5678 9012"
            )

            return

        amount = context.user_data.get(
            "withdraw_amount"
        )

        if not amount:

            context.user_data.pop("mode", None)

            await update.message.reply_text(
                "❌ Pul yechish jarayoni topilmadi.",
                reply_markup=main_menu()
            )

            return

        conn = db()
        cur = conn.cursor()

        try:

            cur.execute("""
                SELECT
                    balance,
                    reserved_balance
                FROM users
                WHERE id = %s
                FOR UPDATE
            """, (user_id,))

            user_balance = cur.fetchone()

            if not user_balance:

                await update.message.reply_text(
                    "❌ Foydalanuvchi topilmadi."
                )

                return

            balance = user_balance[0] or 0
            reserved = user_balance[1] or 0

            available = max(
                0,
                balance - reserved
            )

            if amount > available:

                await update.message.reply_text(
                    "❌ Bu summa endi mavjud emas."
                )

                return

            # Mablag'ni vaqtincha band qilish
            cur.execute("""
                UPDATE users
                SET reserved_balance =
                    reserved_balance + %s
                WHERE id = %s
            """, (
                amount,
                user_id,
            ))

            cur.execute("""
                INSERT INTO withdrawals (
                    user_id,
                    amount,
                    card_number,
                    status
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    'pending'
                )
                RETURNING id
            """, (
                user_id,
                amount,
                card,
            ))

            withdrawal_id = cur.fetchone()[0]

            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            cur.close()
            conn.close()

        context.user_data.pop("mode", None)
        context.user_data.pop(
            "withdraw_amount",
            None
        )

        user_info = get_user(user_id)

        registered_name = (
            user_info[4]
            if user_info and user_info[4]
            else "Noma'lum"
        )

        username = user.username or "-"

        admin_text = (
            f"💳 Yangi pul yechish #{withdrawal_id}\n\n"
            f"👤 Ism: {registered_name}\n"
            f"🔗 Username: "
            f"@{username if username != '-' else '-'}\n"
            f"🆔 Telegram ID: {user_id}\n"
            f"💰 Summa: {format_money(amount)}\n"
            f"💳 Karta: {card}\n"
        )

        try:

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_text,
                reply_markup=withdrawal_menu(
                    withdrawal_id
                )
            )

        except Exception as e:

            logger.error(
                f"Withdrawal admin xabari yuborilmadi: {e}"
            )

            # Admin xabari ketmasa rezervni qaytaramiz
            conn = db()
            cur = conn.cursor()

            try:

                cur.execute("""
                    UPDATE users
                    SET reserved_balance =
                        GREATEST(
                            0,
                            reserved_balance - %s
                        )
                    WHERE id = %s
                """, (
                    amount,
                    user_id,
                ))

                cur.execute("""
                    UPDATE withdrawals
                    SET status = 'rejected'
                    WHERE id = %s
                """, (
                    withdrawal_id,
                ))

                conn.commit()

            except Exception:

                conn.rollback()

            finally:

                cur.close()
                conn.close()

            await update.message.reply_text(
                "❌ So‘rovni yuborishda xatolik yuz berdi. "
                "Iltimos, keyinroq urinib ko‘ring.",
                reply_markup=main_menu()
            )

            return

        await update.message.reply_text(
            "✅ Pul yechish so‘rovingiz qabul qilindi!\n\n"
            f"💰 Summa: {format_money(amount)}\n"
            f"💳 Karta: {mask_card(card)}\n\n"
            "Admin tekshirganidan so‘ng to‘lov amalga oshiriladi.",
            reply_markup=main_menu()
        )

        return

    # =====================================================
    # ADMIN REPLY
    # =====================================================

    if (
        mode == "admin_reply"
        and user_id == ADMIN_ID
    ):

        submission_id = context.user_data.get(
            "reply_submission_id"
        )

        target_user_id = context.user_data.get(
            "reply_user_id"
        )

        if not submission_id or not target_user_id:

            context.user_data.pop(
                "mode",
                None
            )

            await update.message.reply_text(
                "❌ Javob berish ma'lumotlari topilmadi."
            )

            return

        try:

            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "📰 Navoiyliklar.uz\n\n"
                    "💬 Murojaatingizga javob:\n\n"
                    f"{text}"
                )
            )

        except Exception as e:

            logger.error(
                f"Userga admin javobi yuborilmadi: {e}"
            )

            await update.message.reply_text(
                "❌ Foydalanuvchiga javob yuborilmadi."
            )

            return

        conn = db()
        cur = conn.cursor()

        try:

            cur.execute("""
                UPDATE submissions
                SET status = 'answered'
                WHERE id = %s
                AND type = 'appeal'
            """, (
                submission_id,
            ))

            conn.commit()

        except Exception:

            conn.rollback()
            raise

        finally:

            cur.close()
            conn.close()

        context.user_data.pop(
            "mode",
            None
        )

        context.user_data.pop(
            "reply_submission_id",
            None
        )

        context.user_data.pop(
            "reply_user_id",
            None
        )

        await update.message.reply_text(
            f"✅ Murojaat #{submission_id} ga javob yuborildi."
        )

        return

    # =====================================================
    # DEFAULT
    # =====================================================

    await update.message.reply_text(
        "👇 Menyudan kerakli bo‘limni tanlang:",
        reply_markup=main_menu()
    )


# =========================================================
# VIDEO HANDLER
# =========================================================

async def handle_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if context.user_data.get("mode") != "video":
        return

    save_user(
        user.id,
        user.username or "",
        user.full_name or "",
    )

    file_id = None

    if update.message.video:

        file_id = update.message.video.file_id

    elif update.message.document:

        document = update.message.document

        mime_type = document.mime_type or ""

        if mime_type.startswith("video/"):

            file_id = document.file_id

    if not file_id:

        await update.message.reply_text(
            "❌ Iltimos, video fayl yuboring."
        )

        return

    conn = db()
    cur = conn.cursor()

    try:

        cur.execute("""
            INSERT INTO submissions (
                user_id,
                type,
                content,
                status,
                reward
            )
            VALUES (
                %s,
                'video',
                %s,
                'pending',
                0
            )
            RETURNING id
        """, (
            user.id,
            file_id,
        ))

        submission_id = cur.fetchone()[0]

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        cur.close()
        conn.close()

    context.user_data.pop(
        "mode",
        None
    )

    user_info = get_user(user.id)

    registered_name = (
        user_info[4]
        if user_info and user_info[4]
        else "Noma'lum"
    )

    username = user.username or "-"

    caption = (
        f"🎥 Yangi video #{submission_id}\n\n"
        f"👤 Ism: {registered_name}\n"
        f"🔗 Username: "
        f"@{username if username != '-' else '-'}\n"
        f"🆔 Telegram ID: {user.id}\n\n"
        "💰 Mukofotni tanlang:"
    )

    try:

        if update.message.video:

            await context.bot.send_video(
                chat_id=ADMIN_ID,
                video=file_id,
                caption=caption,
                reply_markup=video_reward_menu(
                    submission_id
                )
            )

        else:

            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=file_id,
                caption=caption,
                reply_markup=video_reward_menu(
                    submission_id
                )
            )

    except Exception as e:

        logger.error(
            f"Admin video xabari yuborilmadi: {e}"
        )

        conn = db()
        cur = conn.cursor()

        try:

            cur.execute("""
                UPDATE submissions
                SET status = 'rejected'
                WHERE id = %s
            """, (
                submission_id,
            ))

            conn.commit()

        except Exception:

            conn.rollback()

        finally:

            cur.close()
            conn.close()

        await update.message.reply_text(
            "❌ Videoni yuborishda xatolik yuz berdi. "
            "Iltimos, keyinroq urinib ko‘ring.",
            reply_markup=main_menu()
        )

        return

    await update.message.reply_text(
        "✅ Videongiz qabul qilindi!\n\n"
        "Adminlar videoni ko‘rib chiqadi.\n"
        "Tasdiqlansa, sizga 5 000 – 15 000 so‘m "
        "oralig‘ida mukofot belgilanadi.",
        reply_markup=main_menu()
    )


# =========================================================
# /USERS
# =========================================================

async def users_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Sizda admin huquqi yo‘q."
        )

        return

    conn = db()
    cur = conn.cursor()

    try:

        cur.execute("""
            SELECT COUNT(*)
            FROM users
        """)

        count = cur.fetchone()[0]

    finally:

        cur.close()
        conn.close()

    await update.message.reply_text(
        f"👥 Jami foydalanuvchilar: {count}"
    )


# =========================================================
# /WITHDRAWALS
# =========================================================

async def withdrawals_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Sizda admin huquqi yo‘q."
        )

        return

    conn = db()
    cur = conn.cursor()

    try:

        cur.execute("""
            SELECT
                COUNT(*),
                COALESCE(SUM(amount), 0)
            FROM withdrawals
            WHERE status = 'pending'
        """)

        count, total = cur.fetchone()

    finally:

        cur.close()
        conn.close()

    await update.message.reply_text(
        "💳 Kutilayotgan pul yechishlar\n\n"
        f"📌 Soni: {count}\n"
        f"💰 Jami: {format_money(total)}"
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
            "Environment variable orqali BOT_TOKEN "
            "o‘rnating."
        )

    if not DATABASE_URL:

        raise RuntimeError(
            "DATABASE_URL topilmadi.\n\n"
            "Environment variable orqali DATABASE_URL "
            "o‘rnating."
        )

    # Database yaratish
    init_db()

    # Telegram bot
    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # Commands
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "admin",
            admin_command
        )
    )

    app.add_handler(
        CommandHandler(
            "users",
            users_command
        )
    )

    app.add_handler(
        CommandHandler(
            "withdrawals",
            withdrawals_command
        )
    )

    # Buttons
    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    # Video
    app.add_handler(
        MessageHandler(
            filters.VIDEO | filters.Document.VIDEO,
            handle_video
        )
    )

    # Text
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    # Errors
    app.add_error_handler(
        error_handler
    )

    print("🤖 Navoiyliklar.uz bot ishga tushdi...")
    print("🗄 PostgreSQL database ulandi.")

    app.run_polling()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()