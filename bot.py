import os
import logging
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================================================
# SETTINGS
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")


# =========================================================
# ADMINS
# =========================================================

ADMIN_IDS = [
    7267416938,
    1058849364,
    6820475808,
]


# =========================================================
# VIDEO REWARD
# =========================================================

MIN_VIDEO_REWARD = 15_000
MAX_VIDEO_REWARD = 50_000

VIDEO_REWARDS = [
    15_000,
    20_000,
    30_000,
    40_000,
    50_000,
]


# =========================================================
# WITHDRAWAL
# =========================================================

MIN_WITHDRAW = 15_000


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# ENV CHECK
# =========================================================

if not TOKEN:
    raise ValueError(
        "BOT_TOKEN topilmadi."
    )

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL topilmadi."
    )


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor,
    )


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # USERS
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance BIGINT DEFAULT 0,
            reserved_balance BIGINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # VIDEO SUBMISSIONS
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS video_submissions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            file_id TEXT NOT NULL,
            caption TEXT,
            reward BIGINT DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # APPEALS
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS appeals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            text TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            answer TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # WITHDRAWALS
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount BIGINT NOT NULL,
            card TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()

    cur.close()
    conn.close()


# =========================================================
# USER DATABASE
# =========================================================

def add_or_update_user(user):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO users (
            id,
            username,
            first_name
        )
        VALUES (%s, %s, %s)

        ON CONFLICT (id)
        DO UPDATE SET
            username = EXCLUDED.username,
            first_name = EXCLUDED.first_name
        """,
        (
            user.id,
            user.username,
            user.first_name,
        ),
    )

    conn.commit()

    cur.close()
    conn.close()


# =========================================================
# ADMIN CHECK
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# =========================================================
# FORMAT MONEY
# =========================================================

def money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " so'm"


# =========================================================
# MAIN MENU
# =========================================================

def main_menu():

    keyboard = [

        [
            InlineKeyboardButton(
                "📝 Oddiy murojaat",
                callback_data="appeal",
            )
        ],

        [
            InlineKeyboardButton(
                "🎥 Video sotaman",
                callback_data="sell_video",
            )
        ],

        [
            InlineKeyboardButton(
                "💰 Balansim",
                callback_data="balance",
            )
        ],

        [
            InlineKeyboardButton(
                "💳 Pul yechish",
                callback_data="withdraw",
            )
        ],

    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# BACK MENU
# =========================================================

def back_menu():

    keyboard = [
        [
            InlineKeyboardButton(
                "⬅️ Bosh menyu",
                callback_data="main_menu",
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# ADMIN MENU
# =========================================================

def admin_menu():

    keyboard = [

        [
            InlineKeyboardButton(
                "👥 Foydalanuvchilar",
                callback_data="admin_users",
            )
        ],

        [
            InlineKeyboardButton(
                "🎥 Kutilayotgan videolar",
                callback_data="admin_videos",
            )
        ],

        [
            InlineKeyboardButton(
                "💳 Pul yechishlar",
                callback_data="admin_withdrawals",
            )
        ],

    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# VIDEO REWARD MENU
# =========================================================

def video_reward_menu(submission_id: int):

    keyboard = [

        [
            InlineKeyboardButton(
                "15 000 so'm",
                callback_data=f"reward:{submission_id}:15000",
            ),
            InlineKeyboardButton(
                "20 000 so'm",
                callback_data=f"reward:{submission_id}:20000",
            ),
        ],

        [
            InlineKeyboardButton(
                "30 000 so'm",
                callback_data=f"reward:{submission_id}:30000",
            ),
            InlineKeyboardButton(
                "40 000 so'm",
                callback_data=f"reward:{submission_id}:40000",
            ),
        ],

        [
            InlineKeyboardButton(
                "50 000 so'm",
                callback_data=f"reward:{submission_id}:50000",
            )
        ],

        [
            InlineKeyboardButton(
                "❌ Rad etish",
                callback_data=f"reject_video:{submission_id}",
            )
        ],

    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# WITHDRAWAL MENU
# =========================================================

def withdrawal_menu(withdrawal_id: int):

    keyboard = [

        [
            InlineKeyboardButton(
                "✅ To'landi",
                callback_data=f"withdraw_paid:{withdrawal_id}",
            ),

            InlineKeyboardButton(
                "❌ Rad etish",
                callback_data=f"withdraw_reject:{withdrawal_id}",
            ),
        ]

    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# APPEAL MENU
# =========================================================

def appeal_menu(appeal_id: int):

    keyboard = [

        [
            InlineKeyboardButton(
                "💬 Javob berish",
                callback_data=f"appeal_reply:{appeal_id}",
            )
        ],

        [
            InlineKeyboardButton(
                "❌ Yopish",
                callback_data=f"appeal_close:{appeal_id}",
            )
        ],

    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# SEND MESSAGE TO ADMINS
# =========================================================

async def send_to_admins(
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None,
):

    sent_count = 0

    for admin_id in ADMIN_IDS:

        try:

            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=reply_markup,
            )

            sent_count += 1

        except Exception as e:

            logger.error(
                f"Admin {admin_id} ga xabar yuborilmadi: {e}"
            )

    return sent_count


# =========================================================
# SEND MEDIA TO ADMINS
# =========================================================

async def send_media_to_admins(
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    caption: str,
    reply_markup=None,
    is_video=True,
):

    sent_count = 0

    for admin_id in ADMIN_IDS:

        try:

            if is_video:

                await context.bot.send_video(
                    chat_id=admin_id,
                    video=file_id,
                    caption=caption,
                    reply_markup=reply_markup,
                )

            else:

                await context.bot.send_document(
                    chat_id=admin_id,
                    document=file_id,
                    caption=caption,
                    reply_markup=reply_markup,
                )

            sent_count += 1

        except Exception as e:

            logger.error(
                f"Admin {admin_id} ga media yuborilmadi: {e}"
            )

    return sent_count


# =========================================================
# START
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    add_or_update_user(user)

    context.user_data.clear()

    text = (
        "👋 Assalomu alaykum!\n\n"

        "Bu — Navoiyliklar.uz kanali admin bilan "
        "aloqa boti.\n\n"

        "✉️ Oddiy murojaat — savol, taklif, shikoyat "
        "yoki biror voqea haqida xabar bermoqchi "
        "bo'lsangiz shu tugmani bosing. "
        "Adminlar ko'rib chiqib javob qaytaradi.\n\n"

        "🎥 Video sotaman — o'zingiz suratga olgan "
        "tezkor video bo'lsa, shu tugma orqali "
        "yuborishingiz mumkin.\n\n"

        f"💰 Video mukofoti: {money(MIN_VIDEO_REWARD)}"
        f" — {money(MAX_VIDEO_REWARD)}.\n\n"

        "💳 Pul yechish — balansingizdagi mablag'ni "
        "yechish uchun foydalaniladi.\n\n"

        "👇 Kerakli bo'limni tanlang:"
    )

    await update.message.reply_text(
        text,
        reply_markup=main_menu(),
    )


# =========================================================
# CANCEL
# =========================================================

async def cancel_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data.clear()

    await update.message.reply_text(
        "❌ Joriy amal bekor qilindi.",
        reply_markup=main_menu(),
    )


# =========================================================
# ADMIN COMMAND
# =========================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        await update.message.reply_text(
            "❌ Sizda admin huquqi yo'q."
        )

        return

    await update.message.reply_text(
        "🔐 Admin panel\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=admin_menu(),
    )


# =========================================================
# BALANCE
# =========================================================

async def show_balance(
    query,
    user_id: int,
):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT balance, reserved_balance
        FROM users
        WHERE id = %s
        """,
        (user_id,),
    )

    row = cur.fetchone()

    cur.close()
    conn.close()

    if row:

        balance = row["balance"] or 0
        reserved = row["reserved_balance"] or 0

    else:

        balance = 0
        reserved = 0

    total = balance + reserved

    text = (
        "💰 BALANSINGIZ\n\n"

        f"💵 Mavjud balans: {money(balance)}\n"
        f"🔒 Kutilayotgan mablag': {money(reserved)}\n"
        f"💰 Jami: {money(total)}\n\n"

        "ℹ️ Kutilayotgan mablag' — pul yechish "
        "so'rovi yuborilgan, lekin hali admin "
        "tomonidan yakunlanmagan summa."
    )

    await query.message.reply_text(
        text,
        reply_markup=back_menu(),
    )


# =========================================================
# BUTTON HANDLER
# =========================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    user = query.from_user
    user_id = user.id
    data = query.data

    add_or_update_user(user)

    # =====================================================
    # MAIN MENU
    # =====================================================

    if data == "main_menu":

        context.user_data.clear()

        await query.message.reply_text(
            "🏠 Bosh menyu\n\n"
            "Kerakli bo'limni tanlang:",
            reply_markup=main_menu(),
        )

        return

    # =====================================================
    # BALANCE
    # =====================================================

    if data == "balance":

        await show_balance(
            query,
            user_id,
        )

        return

    # =====================================================
    # APPEAL
    # =====================================================

    if data == "appeal":

        context.user_data.clear()
        context.user_data["mode"] = "appeal"

        await query.message.reply_text(
            "📝 ODDIY MUROJAAT\n\n"

            "Savol, taklif, shikoyat yoki "
            "biror voqea haqida xabaringizni "
            "yozib yuboring.\n\n"

            "Adminlar murojaatingizni ko'rib chiqadi "
            "va imkon qadar javob beradi.\n\n"

            "❌ Bekor qilish: /cancel",
            reply_markup=back_menu(),
        )

        return

    # =====================================================
    # SELL VIDEO
    # =====================================================

    if data == "sell_video":

        context.user_data.clear()
        context.user_data["mode"] = "video"

        await query.message.reply_text(
            "🎥 VIDEO SOTISH\n\n"

            "O'zingiz suratga olgan tezkor videoni "
            "shu yerga yuboring.\n\n"

            f"💰 Mukofot: {money(MIN_VIDEO_REWARD)}"
            f" — {money(MAX_VIDEO_REWARD)}.\n\n"

            "Adminlar videoni ko'rib chiqadi va "
            "mos mukofotni belgilaydi.\n\n"

            "📌 Video bilan birga qisqa izoh ham "
            "yozishingiz mumkin.\n\n"

            "❌ Bekor qilish: /cancel",
            reply_markup=back_menu(),
        )

        return

    # =====================================================
    # WITHDRAW
    # =====================================================

    if data == "withdraw":

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT balance
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        )

        row = cur.fetchone()

        cur.close()
        conn.close()

        balance = row["balance"] if row else 0

        if balance < MIN_WITHDRAW:

            await query.message.reply_text(
                "❌ Pul yechish uchun balansingizda "
                f"kamida {money(MIN_WITHDRAW)} bo'lishi kerak.\n\n"

                f"💰 Hozirgi balans: {money(balance)}",
                reply_markup=back_menu(),
            )

            return

        context.user_data.clear()
        context.user_data["mode"] = "withdraw_amount"

        await query.message.reply_text(
            "💳 PUL YECHISH\n\n"

            f"💰 Mavjud balans: {money(balance)}\n"
            f"📌 Minimal summa: {money(MIN_WITHDRAW)}\n\n"

            "Qancha pul yechmoqchi ekaningizni "
            "raqam bilan yozing.\n\n"

            "Masalan:\n"
            "15000\n"
            "30000\n"
            "50000\n\n"

            "❌ Bekor qilish: /cancel",
            reply_markup=back_menu(),
        )

        return

    # =====================================================
    # ADMIN CHECK
    # =====================================================

    if not is_admin(user_id):
        return

    # =====================================================
    # ADMIN USERS
    # =====================================================

    if data == "admin_users":

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(balance), 0) AS balance,
                COALESCE(SUM(reserved_balance), 0) AS reserved
            FROM users
            """
        )

        row = cur.fetchone()

        cur.close()
        conn.close()

        await query.message.reply_text(
            "👥 FOYDALANUVCHILAR\n\n"

            f"👤 Jami: {row['total']}\n"
            f"💰 Balanslar: {money(row['balance'])}\n"
            f"🔒 Rezerv: {money(row['reserved'])}",
            reply_markup=admin_menu(),
        )

        return

    # =====================================================
    # ADMIN VIDEOS
    # =====================================================

    if data == "admin_videos":

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT COUNT(*) AS total
            FROM video_submissions
            WHERE status = 'pending'
            """
        )

        row = cur.fetchone()

        cur.close()
        conn.close()

        await query.message.reply_text(
            "🎥 KUTILAYOTGAN VIDEOLAR\n\n"
            f"📦 Kutilayotgan videolar: {row['total']}\n\n"
            "Yangi video kelganda u avtomatik "
            "ravishda adminlarga yuboriladi.",
            reply_markup=admin_menu(),
        )

        return

    # =====================================================
    # ADMIN WITHDRAWALS
    # =====================================================

    if data == "admin_withdrawals":

        await send_pending_withdrawals(
            query.message,
            context,
        )

        return

    # =====================================================
    # VIDEO REWARD
    # =====================================================

    if data.startswith("reward:"):

        parts = data.split(":")

        submission_id = int(parts[1])
        reward = int(parts[2])

        if reward not in VIDEO_REWARDS:

            await query.message.reply_text(
                "❌ Noto'g'ri mukofot."
            )

            return

        conn = get_db()
        cur = conn.cursor()

        try:

            cur.execute(
                """
                SELECT *
                FROM video_submissions
                WHERE id = %s
                FOR UPDATE
                """,
                (submission_id,),
            )

            submission = cur.fetchone()

            if not submission:

                await query.message.reply_text(
                    "❌ Video topilmadi."
                )

                conn.rollback()
                return

            if submission["status"] != "pending":

                await query.message.reply_text(
                    "⚠️ Bu video allaqachon ko'rib chiqilgan."
                )

                conn.rollback()
                return

            cur.execute(
                """
                UPDATE video_submissions
                SET
                    reward = %s,
                    status = 'approved'
                WHERE id = %s
                """,
                (
                    reward,
                    submission_id,
                ),
            )

            cur.execute(
                """
                UPDATE users
                SET balance = balance + %s
                WHERE id = %s
                """,
                (
                    reward,
                    submission["user_id"],
                ),
            )

            conn.commit()

            await query.message.edit_reply_markup(
                reply_markup=None
            )

            await query.message.reply_text(
                "✅ VIDEO TASDIQLANDI\n\n"
                f"💰 Mukofot: {money(reward)}"
            )

            try:

                await context.bot.send_message(
                    chat_id=submission["user_id"],
                    text=(
                        "🎉 Videongiz tasdiqlandi!\n\n"
                        f"💰 Sizga {money(reward)} "
                        "qo'shildi.\n\n"
                        "💰 Balansingizni botdagi "
                        "'Balansim' bo'limidan ko'rishingiz mumkin."
                    ),
                )

            except Exception as e:

                logger.error(
                    f"Reward xabari yuborilmadi: {e}"
                )

        except Exception:

            conn.rollback()

            logger.exception(
                "Video reward xatosi"
            )

            await query.message.reply_text(
                "❌ Xatolik yuz berdi."
            )

        finally:

            cur.close()
            conn.close()

        return

    # =====================================================
    # REJECT VIDEO
    # =====================================================

    if data.startswith("reject_video:"):

        submission_id = int(
            data.split(":")[1]
        )

        conn = get_db()
        cur = conn.cursor()

        try:

            cur.execute(
                """
                SELECT *
                FROM video_submissions
                WHERE id = %s
                FOR UPDATE
                """,
                (submission_id,),
            )

            submission = cur.fetchone()

            if not submission:

                await query.message.reply_text(
                    "❌ Video topilmadi."
                )

                conn.rollback()
                return

            if submission["status"] != "pending":

                await query.message.reply_text(
                    "⚠️ Bu video allaqachon ko'rib chiqilgan."
                )

                conn.rollback()
                return

            cur.execute(
                """
                UPDATE video_submissions
                SET status = 'rejected'
                WHERE id = %s
                """,
                (submission_id,),
            )

            conn.commit()

            await query.message.edit_reply_markup(
                reply_markup=None
            )

            await query.message.reply_text(
                "❌ Video rad etildi."
            )

            try:

                await context.bot.send_message(
                    chat_id=submission["user_id"],
                    text=(
                        "❌ Afsuski, yuborgan videongiz "
                        "admin tomonidan rad etildi."
                    ),
                )

            except Exception as e:

                logger.error(
                    f"Reject xabari yuborilmadi: {e}"
                )

        except Exception:

            conn.rollback()

            logger.exception(
                "Video reject xatosi"
            )

            await query.message.reply_text(
                "❌ Xatolik yuz berdi."
            )

        finally:

            cur.close()
            conn.close()

        return

    # =====================================================
    # WITHDRAW PAID
    # =====================================================

    if data.startswith("withdraw_paid:"):

        withdrawal_id = int(
            data.split(":")[1]
        )

        conn = get_db()
        cur = conn.cursor()

        try:

            cur.execute(
                """
                SELECT *
                FROM withdrawals
                WHERE id = %s
                FOR UPDATE
                """,
                (withdrawal_id,),
            )

            withdrawal = cur.fetchone()

            if not withdrawal:

                await query.message.reply_text(
                    "❌ Pul yechish so'rovi topilmadi."
                )

                conn.rollback()
                return

            if withdrawal["status"] != "pending":

                await query.message.reply_text(
                    "⚠️ Bu so'rov allaqachon ko'rib chiqilgan."
                )

                conn.rollback()
                return

            cur.execute(
                """
                UPDATE withdrawals
                SET status = 'paid'
                WHERE id = %s
                """,
                (withdrawal_id,),
            )

            cur.execute(
                """
                UPDATE users
                SET reserved_balance =
                    GREATEST(
                        reserved_balance - %s,
                        0
                    )
                WHERE id = %s
                """,
                (
                    withdrawal["amount"],
                    withdrawal["user_id"],
                ),
            )

            conn.commit()

            await query.message.edit_reply_markup(
                reply_markup=None
            )

            await query.message.reply_text(
                "✅ Pul yechish tasdiqlandi."
            )

            try:

                await context.bot.send_message(
                    chat_id=withdrawal["user_id"],
                    text=(
                        "✅ Pul yechish so'rovingiz "
                        "to'landi.\n\n"
                        f"💰 Summa: {money(withdrawal['amount'])}"
                    ),
                )

            except Exception as e:

                logger.error(
                    f"Paid xabari yuborilmadi: {e}"
                )

        except Exception:

            conn.rollback()

            logger.exception(
                "Withdrawal paid xatosi"
            )

            await query.message.reply_text(
                "❌ Xatolik yuz berdi."
            )

        finally:

            cur.close()
            conn.close()

        return

    # =====================================================
    # WITHDRAW REJECT
    # =====================================================

    if data.startswith("withdraw_reject:"):

        withdrawal_id = int(
            data.split(":")[1]
        )

        conn = get_db()
        cur = conn.cursor()

        try:

            cur.execute(
                """
                SELECT *
                FROM withdrawals
                WHERE id = %s
                FOR UPDATE
                """,
                (withdrawal_id,),
            )

            withdrawal = cur.fetchone()

            if not withdrawal:

                await query.message.reply_text(
                    "❌ So'rov topilmadi."
                )

                conn.rollback()
                return

            if withdrawal["status"] != "pending":

                await query.message.reply_text(
                    "⚠️ Bu so'rov allaqachon ko'rib chiqilgan."
                )

                conn.rollback()
                return

            cur.execute(
                """
                UPDATE withdrawals
                SET status = 'rejected'
                WHERE id = %s
                """,
                (withdrawal_id,),
            )

            cur.execute(
                """
                UPDATE users
                SET
                    balance = balance + %s,
                    reserved_balance =
                        GREATEST(
                            reserved_balance - %s,
                            0
                        )
                WHERE id = %s
                """,
                (
                    withdrawal["amount"],
                    withdrawal["amount"],
                    withdrawal["user_id"],
                ),
            )

            conn.commit()

            await query.message.edit_reply_markup(
                reply_markup=None
            )

            await query.message.reply_text(
                "❌ Pul yechish so'rovi rad etildi."
            )

            try:

                await context.bot.send_message(
                    chat_id=withdrawal["user_id"],
                    text=(
                        "❌ Pul yechish so'rovingiz "
                        "rad etildi.\n\n"
                        f"💰 {money(withdrawal['amount'])} "
                        "balansingizga qaytarildi."
                    ),
                )

            except Exception as e:

                logger.error(
                    f"Reject withdrawal xabari yuborilmadi: {e}"
                )

        except Exception:

            conn.rollback()

            logger.exception(
                "Withdrawal reject xatosi"
            )

            await query.message.reply_text(
                "❌ Xatolik yuz berdi."
            )

        finally:

            cur.close()
            conn.close()

        return

    # =====================================================
    # APPEAL REPLY
    # =====================================================

    if data.startswith("appeal_reply:"):

        appeal_id = int(
            data.split(":")[1]
        )

        context.user_data["mode"] = "admin_reply"
        context.user_data["appeal_id"] = appeal_id

        await query.message.reply_text(
            "💬 Foydalanuvchiga yubormoqchi "
            "bo'lgan javobingizni yozing.\n\n"
            "❌ Bekor qilish: /cancel"
        )

        return

    # =====================================================
    # APPEAL CLOSE
    # =====================================================

    if data.startswith("appeal_close:"):

        appeal_id = int(
            data.split(":")[1]
        )

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM appeals
            WHERE id = %s
            """,
            (appeal_id,),
        )

        appeal = cur.fetchone()

        if not appeal:

            cur.close()
            conn.close()

            await query.message.reply_text(
                "❌ Murojaat topilmadi."
            )

            return

        cur.execute(
            """
            UPDATE appeals
            SET status = 'closed'
            WHERE id = %s
            """,
            (appeal_id,),
        )

        conn.commit()

        cur.close()
        conn.close()

        await query.message.edit_reply_markup(
            reply_markup=None
        )

        await query.message.reply_text(
            "✅ Murojaat yopildi."
        )

        try:

            await context.bot.send_message(
                chat_id=appeal["user_id"],
                text="ℹ️ Sizning murojaatingiz yopildi.",
            )

        except Exception as e:

            logger.error(
                f"Appeal close xabari yuborilmadi: {e}"
            )

        return


# =========================================================
# MESSAGE HANDLER
# =========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user
    user_id = user.id

    text = update.message.text or ""

    add_or_update_user(user)

    mode = context.user_data.get("mode")

    # =====================================================
    # ADMIN REPLY
    # =====================================================

    if (
        mode == "admin_reply"
        and is_admin(user_id)
    ):

        appeal_id = context.user_data.get(
            "appeal_id"
        )

        if not appeal_id:
            return

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM appeals
            WHERE id = %s
            FOR UPDATE
            """,
            (appeal_id,),
        )

        appeal = cur.fetchone()

        if not appeal:

            conn.rollback()
            cur.close()
            conn.close()

            await update.message.reply_text(
                "❌ Murojaat topilmadi."
            )

            return

        if appeal["status"] != "pending":

            conn.rollback()
            cur.close()
            conn.close()

            await update.message.reply_text(
                "⚠️ Bu murojaat allaqachon yopilgan."
            )

            return

        cur.execute(
            """
            UPDATE appeals
            SET
                status = 'answered',
                answer = %s
            WHERE id = %s
            """,
            (
                text,
                appeal_id,
            ),
        )

        conn.commit()

        cur.close()
        conn.close()

        try:

            await context.bot.send_message(
                chat_id=appeal["user_id"],
                text=(
                    "💬 MUROJAATINGIZGA JAVOB\n\n"
                    f"{text}"
                ),
            )

        except Exception as e:

            logger.error(
                f"Appeal javobi yuborilmadi: {e}"
            )

        context.user_data.clear()

        await update.message.reply_text(
            "✅ Javob foydalanuvchiga yuborildi.",
            reply_markup=admin_menu(),
        )

        return

    # =====================================================
    # NORMAL APPEAL
    # =====================================================

    if mode == "appeal":

        if not text.strip():

            await update.message.reply_text(
                "❌ Murojaat matnini yozing."
            )

            return

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO appeals (
                user_id,
                text
            )
            VALUES (%s, %s)
            RETURNING id
            """,
            (
                user_id,
                text.strip(),
            ),
        )

        appeal = cur.fetchone()

        conn.commit()

        cur.close()
        conn.close()

        appeal_id = appeal["id"]

        context.user_data.clear()

        admin_text = (
            "📝 YANGI MUROJAAT\n\n"

            f"👤 Ism: {user.first_name}\n"
            f"🆔 ID: {user_id}\n"
            f"🔗 Username: "
            f"@{user.username if user.username else 'yo‘q'}\n\n"

            f"💬 Murojaat:\n{text}"
        )

        await send_to_admins(
            context,
            admin_text,
            reply_markup=appeal_menu(
                appeal_id
            ),
        )

        await update.message.reply_text(
            "✅ Murojaatingiz qabul qilindi.\n\n"
            "Adminlar ko'rib chiqadi va javob beradi.",
            reply_markup=main_menu(),
        )

        return

    # =====================================================
    # WITHDRAW AMOUNT
    # =====================================================

    if mode == "withdraw_amount":

        try:

            amount = int(
                text.replace(" ", "")
                .replace(",", "")
                .replace(".", "")
            )

        except ValueError:

            await update.message.reply_text(
                "❌ Summani faqat raqam bilan yozing.\n\n"
                "Masalan: 30000"
            )

            return

        if amount < MIN_WITHDRAW:

            await update.message.reply_text(
                f"❌ Minimal summa: "
                f"{money(MIN_WITHDRAW)}"
            )

            return

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT balance
            FROM users
            WHERE id = %s
            FOR UPDATE
            """,
            (user_id,),
        )

        row = cur.fetchone()

        cur.close()
        conn.close()

        balance = row["balance"] if row else 0

        if amount > balance:

            await update.message.reply_text(
                "❌ Balansingizda yetarli mablag' yo'q.\n\n"
                f"💰 Mavjud: {money(balance)}"
            )

            return

        context.user_data["withdraw_amount"] = amount
        context.user_data["mode"] = "withdraw_card"

        await update.message.reply_text(
            "💳 KARTA MA'LUMOTI\n\n"
            f"💰 Yechiladigan summa: {money(amount)}\n\n"
            "Pul o'tkaziladigan karta raqamini "
            "yuboring.\n\n"
            "❌ Bekor qilish: /cancel"
        )

        return

    # =====================================================
    # WITHDRAW CARD
    # =====================================================

    if mode == "withdraw_card":

        amount = context.user_data.get(
            "withdraw_amount"
        )

        if not amount:

            context.user_data.clear()

            await update.message.reply_text(
                "❌ Jarayon tugadi. Qaytadan urinib ko'ring.",
                reply_markup=main_menu(),
            )

            return

        card = text.strip()

        if len(card) < 8:

            await update.message.reply_text(
                "❌ Karta ma'lumoti noto'g'ri.\n"
                "Qaytadan yuboring."
            )

            return

        conn = get_db()
        cur = conn.cursor()

        try:

            cur.execute(
                """
                SELECT balance
                FROM users
                WHERE id = %s
                FOR UPDATE
                """,
                (user_id,),
            )

            user_row = cur.fetchone()

            if (
                not user_row
                or user_row["balance"] < amount
            ):

                conn.rollback()

                await update.message.reply_text(
                    "❌ Balansingizda yetarli mablag' yo'q."
                )

                return

            # Reserve money
            cur.execute(
                """
                UPDATE users
                SET
                    balance = balance - %s,
                    reserved_balance =
                        reserved_balance + %s
                WHERE id = %s
                """,
                (
                    amount,
                    amount,
                    user_id,
                ),
            )

            # Create withdrawal
            cur.execute(
                """
                INSERT INTO withdrawals (
                    user_id,
                    amount,
                    card
                )
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (
                    user_id,
                    amount,
                    card,
                ),
            )

            withdrawal = cur.fetchone()

            conn.commit()

            withdrawal_id = withdrawal["id"]

            context.user_data.clear()

            admin_text = (
                "💳 YANGI PUL YECHISH SO'ROVI\n\n"

                f"👤 Ism: {user.first_name}\n"
                f"🆔 ID: {user_id}\n"
                f"🔗 Username: "
                f"@{user.username if user.username else 'yo‘q'}\n\n"

                f"💰 Summa: {money(amount)}\n"
                f"💳 Karta: {card}"
            )

            await send_to_admins(
                context,
                admin_text,
                reply_markup=withdrawal_menu(
                    withdrawal_id
                ),
            )

            await update.message.reply_text(
                "✅ Pul yechish so'rovingiz yuborildi.\n\n"

                f"💰 Summa: {money(amount)}\n"

                "⏳ Admin tekshiruvini kuting.",
                reply_markup=main_menu(),
            )

        except Exception:

            conn.rollback()

            logger.exception(
                "Withdrawal create xatosi"
            )

            await update.message.reply_text(
                "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring."
            )

        finally:

            cur.close()
            conn.close()

        return

    # =====================================================
    # UNKNOWN TEXT
    # =====================================================

    await update.message.reply_text(
        "ℹ️ Iltimos, quyidagi menyudan kerakli "
        "bo'limni tanlang.",
        reply_markup=main_menu(),
    )


# =========================================================
# VIDEO HANDLER
# =========================================================

async def handle_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    add_or_update_user(user)

    mode = context.user_data.get("mode")

    if mode != "video":

        await update.message.reply_text(
            "❌ Avval '🎥 Video sotaman' "
            "bo'limini tanlang.",
            reply_markup=main_menu(),
        )

        return

    file_id = None
    is_video = False

    if update.message.video:

        file_id = update.message.video.file_id
        is_video = True

    elif update.message.document:

        file_id = update.message.document.file_id
        is_video = False

    if not file_id:

        await update.message.reply_text(
            "❌ Video fayl yuboring."
        )

        return

    caption = update.message.caption or ""

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO video_submissions (
            user_id,
            file_id,
            caption
        )
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (
            user.id,
            file_id,
            caption,
        ),
    )

    submission = cur.fetchone()

    conn.commit()

    cur.close()
    conn.close()

    submission_id = submission["id"]

    admin_caption = (
        "🎥 YANGI VIDEO\n\n"

        f"👤 Ism: {user.first_name}\n"
        f"🆔 ID: {user.id}\n"
        f"🔗 Username: "
        f"@{user.username if user.username else 'yo‘q'}\n\n"
    )

    if caption:

        admin_caption += (
            f"📝 Izoh:\n{caption}\n\n"
        )

    admin_caption += (
        "💰 Mukofotni tanlang:\n"
        f"{money(MIN_VIDEO_REWARD)}"
        " — "
        f"{money(MAX_VIDEO_REWARD)}"
    )

    sent_count = await send_media_to_admins(
        context=context,
        file_id=file_id,
        caption=admin_caption,
        reply_markup=video_reward_menu(
            submission_id
        ),
        is_video=is_video,
    )

    if sent_count == 0:

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE video_submissions
            SET status = 'rejected'
            WHERE id = %s
            """,
            (submission_id,),
        )

        conn.commit()

        cur.close()
        conn.close()

        await update.message.reply_text(
            "❌ Videoni adminlarga yuborishda "
            "xatolik yuz berdi."
        )

        return

    context.user_data.clear()

    await update.message.reply_text(
        "✅ Videongiz qabul qilindi!\n\n"

        "📨 Video adminlarga yuborildi.\n"

        f"💰 Mukofot: {money(MIN_VIDEO_REWARD)}"
        f" — {money(MAX_VIDEO_REWARD)}.\n\n"

        "Adminlar tekshirganidan keyin "
        "balansingizga qo'shiladi.",
        reply_markup=main_menu(),
    )


# =========================================================
# USERS COMMAND
# =========================================================

async def users_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        await update.message.reply_text(
            "❌ Sizda admin huquqi yo'q."
        )

        return

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(balance), 0) AS balance,
            COALESCE(SUM(reserved_balance), 0) AS reserved
        FROM users
        """
    )

    row = cur.fetchone()

    cur.close()
    conn.close()

    await update.message.reply_text(
        "👥 STATISTIKA\n\n"

        f"👤 Foydalanuvchilar: {row['total']}\n"
        f"💰 Balanslar: {money(row['balance'])}\n"
        f"🔒 Rezerv: {money(row['reserved'])}",
        reply_markup=admin_menu(),
    )


# =========================================================
# WITHDRAWALS COMMAND
# =========================================================

async def withdrawals_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        await update.message.reply_text(
            "❌ Sizda admin huquqi yo'q."
        )

        return

    await send_pending_withdrawals(
        update.message,
        context,
    )


# =========================================================
# SEND PENDING WITHDRAWALS
# =========================================================

async def send_pending_withdrawals(
    message,
    context,
):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            w.*,
            u.username,
            u.first_name
        FROM withdrawals w

        LEFT JOIN users u
            ON u.id = w.user_id

        WHERE w.status = 'pending'

        ORDER BY w.created_at ASC
        """
    )

    rows = cur.fetchall()

    cur.close()
    conn.close()

    if not rows:

        await message.reply_text(
            "✅ Hozircha kutilayotgan "
            "pul yechish so'rovlari yo'q."
        )

        return

    await message.reply_text(
        f"💳 Kutilayotgan so'rovlar: {len(rows)}"
    )

    for row in rows:

        text = (
            "💳 PUL YECHISH\n\n"

            f"👤 Ism: {row['first_name']}\n"
            f"🆔 ID: {row['user_id']}\n"
            f"🔗 Username: "
            f"@{row['username'] if row['username'] else 'yo‘q'}\n\n"

            f"💰 Summa: {money(row['amount'])}\n"
            f"💳 Karta: {row['card']}"
        )

        await message.reply_text(
            text,
            reply_markup=withdrawal_menu(
                row["id"]
            ),
        )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.exception(
        "Botda xatolik yuz berdi:",
        exc_info=context.error,
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print("====================================")
    print("Navoiyliklar.uz Bot ishga tushmoqda")
    print("====================================")

    # Database
    init_db()

    print("✅ PostgreSQL ulandi")

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    # =====================================================
    # COMMANDS
    # =====================================================

    application.add_handler(
        CommandHandler(
            "start",
            start_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "cancel",
            cancel_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "users",
            users_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "withdrawals",
            withdrawals_command,
        )
    )

    # =====================================================
    # CALLBACK BUTTONS
    # =====================================================

    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    # =====================================================
    # VIDEO / DOCUMENT
    # =====================================================

    application.add_handler(
        MessageHandler(
            filters.VIDEO | filters.Document.ALL,
            handle_video,
        )
    )

    # =====================================================
    # TEXT
    # =====================================================

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    # =====================================================
    # ERROR
    # =====================================================

    application.add_error_handler(
        error_handler
    )

    # =====================================================
    # START
    # =====================================================

    print("====================================")
    print("✅ Navoiyliklar.uz Bot ishga tushdi")
    print("====================================")

    print("Adminlar:")

    for admin_id in ADMIN_IDS:
        print(f" - {admin_id}")

    print("====================================")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()