import os
import logging
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
# 3 TA ADMIN
# =========================================================

ADMIN_IDS = [
    7267416938,
    1058849364,
    6820475808,
]

MIN_VIDEO_REWARD = 5_000
MAX_VIDEO_REWARD = 15_000
MIN_WITHDRAW = 5_000

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# CHECK ENV
# =========================================================

if not TOKEN:
    raise ValueError("BOT_TOKEN topilmadi.")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL topilmadi.")


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # USERS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance BIGINT DEFAULT 0,
            reserved_balance BIGINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # VIDEO SUBMISSIONS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS video_submissions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            file_id TEXT NOT NULL,
            caption TEXT,
            reward BIGINT DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # APPEALS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appeals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            text TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            answer TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # WITHDRAWALS
    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount BIGINT NOT NULL,
            card TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


# =========================================================
# USER
# =========================================================

def add_or_update_user(user):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
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
    """, (
        user.id,
        user.username,
        user.first_name,
    ))

    conn.commit()
    cur.close()
    conn.close()


# =========================================================
# ADMIN HELPERS
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def send_to_admins(
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup=None
):
    """
    Barcha 3 ta adminlarga text xabar yuboradi.
    """

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=reply_markup,
            )

        except Exception as e:
            logger.error(
                f"Admin {admin_id} ga xabar yuborilmadi: {e}"
            )


async def send_media_to_admins(
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    caption: str,
    reply_markup=None,
    is_video=True
):
    """
    Barcha 3 ta adminlarga video/document yuboradi.
    """

    sent_to_any_admin = False

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

            sent_to_any_admin = True

        except Exception as e:

            logger.error(
                f"Admin {admin_id} ga media yuborilmadi: {e}"
            )

    return sent_to_any_admin


# =========================================================
# MAIN MENU
# =========================================================

def main_menu():

    keyboard = [

        [
            InlineKeyboardButton(
                "📝 Oddiy murojaat",
                callback_data="appeal"
            )
        ],

        [
            InlineKeyboardButton(
                "🎥 Video sotaman",
                callback_data="sell_video"
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


# =========================================================
# ADMIN MENU
# =========================================================

def admin_menu():

    keyboard = [

        [
            InlineKeyboardButton(
                "👥 Foydalanuvchilar",
                callback_data="admin_users"
            )
        ],

        [
            InlineKeyboardButton(
                "💳 Pul yechishlar",
                callback_data="admin_withdrawals"
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
                "10 000 so'm",
                callback_data=f"reward:{submission_id}:10000"
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
                callback_data=f"reject_video:{submission_id}"
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
                callback_data=f"withdraw_paid:{withdrawal_id}"
            ),

            InlineKeyboardButton(
                "❌ Rad etish",
                callback_data=f"withdraw_reject:{withdrawal_id}"
            ),
        ]

    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# APPEAL MENU
# =========================================================

def appeal_menu(submission_id):

    keyboard = [

        [
            InlineKeyboardButton(
                "💬 Javob berish",
                callback_data=f"appeal_reply:{submission_id}"
            )
        ],

        [
            InlineKeyboardButton(
                "❌ Yopish",
                callback_data=f"appeal_close:{submission_id}"
            )
        ],

    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# START
# =========================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    add_or_update_user(user)

    await update.message.reply_text(

        "👋 Assalomu alaykum!\n\n"
        "🌐 Navoiyliklar.uz axborot agentligi\n\n"
        "Kerakli bo'limni tanlang:",

        reply_markup=main_menu()
    )


# =========================================================
# ADMIN COMMAND
# =========================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
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

    user = query.from_user

    user_id = user.id

    data = query.data

    add_or_update_user(user)

    # =====================================================
    # BALANCE
    # =====================================================

    if data == "balance":

        conn = get_db()

        cur = conn.cursor()

        cur.execute("""
            SELECT balance, reserved_balance
            FROM users
            WHERE id = %s
        """, (user_id,))

        row = cur.fetchone()

        cur.close()

        conn.close()

        if not row:

            balance = 0
            reserved = 0

        else:

            balance = row["balance"] or 0
            reserved = row["reserved_balance"] or 0

        await query.message.reply_text(

            "💰 Balansingiz\n\n"

            f"💵 Asosiy balans: {balance:,} so'm\n"
            f"🔒 Kutayotgan mablag': {reserved:,} so'm\n\n"

            f"💰 Jami: {balance + reserved:,} so'm"
        )

        return

    # =====================================================
    # APPEAL
    # =====================================================

    if data == "appeal":

        context.user_data["mode"] = "appeal"

        await query.message.reply_text(

            "📝 Oddiy murojaat\n\n"
            "Murojaatingizni yozib yuboring."
        )

        return

    # =====================================================
    # SELL VIDEO
    # =====================================================

    if data == "sell_video":

        context.user_data["mode"] = "video"

        await query.message.reply_text(

            "🎥 Video sotish\n\n"

            "Videoni yuboring.\n\n"

            "Admin video ko'rib chiqib, "
            "5 000 - 15 000 so'm oralig'ida "
            "mukofot belgilaydi."
        )

        return

    # =====================================================
    # WITHDRAW
    # =====================================================

    if data == "withdraw":

        conn = get_db()

        cur = conn.cursor()

        cur.execute("""
            SELECT balance, reserved_balance
            FROM users
            WHERE id = %s
        """, (user_id,))

        row = cur.fetchone()

        cur.close()

        conn.close()

        balance = row["balance"] if row else 0

        if balance < MIN_WITHDRAW:

            await query.message.reply_text(

                "❌ Pul yechish uchun balansingizda "
                f"kamida {MIN_WITHDRAW:,} so'm bo'lishi kerak."
            )

            return

        context.user_data["mode"] = "withdraw_amount"

        await query.message.reply_text(

            "💳 Pul yechish\n\n"

            f"Minimal summa: {MIN_WITHDRAW:,} so'm\n\n"

            "Qancha pul yechmoqchi ekaningizni yozing:"
        )

        return

    # =====================================================
    # ADMIN AREA
    # =====================================================

    if not is_admin(user_id):

        return

    # =====================================================
    # ADMIN USERS
    # =====================================================

    if data == "admin_users":

        conn = get_db()

        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*) AS count
            FROM users
        """)

        row = cur.fetchone()

        cur.close()

        conn.close()

        count = row["count"]

        await query.message.reply_text(

            "👥 Foydalanuvchilar\n\n"
            f"Jami foydalanuvchilar: {count}"
        )

        return

    # =====================================================
    # ADMIN WITHDRAWALS
    # =====================================================

    if data == "admin_withdrawals":

        await send_pending_withdrawals(
            query.message,
            context
        )

        return

    # =====================================================
    # VIDEO REWARD
    # =====================================================

    if data.startswith("reward:"):

        parts = data.split(":")

        submission_id = int(parts[1])

        reward = int(parts[2])

        if reward < MIN_VIDEO_REWARD:

            await query.message.reply_text(
                "❌ Mukofot juda kam."
            )

            return

        if reward > MAX_VIDEO_REWARD:

            await query.message.reply_text(
                "❌ Mukofot juda katta."
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
                (submission_id,)
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
                SET reward = %s,
                    status = 'approved'
                WHERE id = %s
                """,
                (
                    reward,
                    submission_id
                )
            )

            cur.execute(
                """
                UPDATE users
                SET balance = balance + %s
                WHERE id = %s
                """,
                (
                    reward,
                    submission["user_id"]
                )
            )

            conn.commit()

            await query.message.edit_reply_markup(
                reply_markup=None
            )

            await query.message.reply_text(

                "✅ Video tasdiqlandi.\n"

                f"💰 Mukofot: {reward:,} so'm"
            )

            try:

                await context.bot.send_message(

                    chat_id=submission["user_id"],

                    text=(

                        "🎉 Videongiz tasdiqlandi!\n\n"

                        f"💰 Sizga {reward:,} so'm "
                        "qo'shildi."
                    )
                )

            except Exception as e:

                logger.error(
                    f"Userga reward xabari yuborilmadi: {e}"
                )

        except Exception as e:

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
                (submission_id,)
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
                (submission_id,)
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
                        "rad etildi."
                    )
                )

            except Exception as e:

                logger.error(
                    f"Userga reject xabari yuborilmadi: {e}"
                )

        except Exception as e:

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
                (withdrawal_id,)
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
                (withdrawal_id,)
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
                    withdrawal["user_id"]
                )
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

                        f"💰 Summa: "
                        f"{withdrawal['amount']:,} so'm"
                    )
                )

            except Exception as e:

                logger.error(
                    f"Withdrawal paid xabari yuborilmadi: {e}"
                )

        except Exception as e:

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
                (withdrawal_id,)
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
                (withdrawal_id,)
            )

            cur.execute(
                """
                UPDATE users
                SET balance = balance + %s,
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
                    withdrawal["user_id"]
                )
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

                        f"💰 {withdrawal['amount']:,} so'm "
                        "balansingizga qaytarildi."
                    )
                )

            except Exception as e:

                logger.error(
                    f"Withdrawal reject xabari yuborilmadi: {e}"
                )

        except Exception as e:

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

        submission_id = int(
            data.split(":")[1]
        )

        context.user_data["mode"] = "admin_reply"

        context.user_data["appeal_id"] = submission_id

        await query.message.reply_text(

            "💬 Foydalanuvchiga yubormoqchi "
            "bo'lgan javobingizni yozing:"
        )

        return

    # =====================================================
    # APPEAL CLOSE
    # =====================================================

    if data.startswith("appeal_close:"):

        submission_id = int(
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
            (submission_id,)
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
            (submission_id,)
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

                text="ℹ️ Sizning murojaatingiz yopildi."
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
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    user_id = user.id

    text = update.message.text

    add_or_update_user(user)

    mode = context.user_data.get("mode")

    # =====================================================
    # ADMIN REPLY
    # =====================================================

    if (
        mode == "admin_reply"
        and user_id in ADMIN_IDS
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
            (appeal_id,)
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
            SET status = 'answered',
                answer = %s
            WHERE id = %s
            """,
            (
                text,
                appeal_id
            )
        )

        conn.commit()

        cur.close()

        conn.close()

        try:

            await context.bot.send_message(

                chat_id=appeal["user_id"],

                text=(
                    "💬 Murojaatingizga javob:\n\n"
                    f"{text}"
                )
            )

        except Exception as e:

            logger.error(
                f"Appeal javobi yuborilmadi: {e}"
            )

        context.user_data.pop(
            "mode",
            None
        )

        context.user_data.pop(
            "appeal_id",
            None
        )

        await update.message.reply_text(
            "✅ Javob foydalanuvchiga yuborildi."
        )

        return

    # =====================================================
    # NORMAL APPEAL
    # =====================================================

    if mode == "appeal":

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
                text
            )
        )

        appeal = cur.fetchone()

        conn.commit()

        cur.close()

        conn.close()

        appeal_id = appeal["id"]

        context.user_data.pop(
            "mode",
            None
        )

        admin_text = (

            "📝 Yangi murojaat!\n\n"

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
            )
        )

        await update.message.reply_text(

            "✅ Murojaatingiz qabul qilindi.\n\n"
            "Tez orada javob beriladi."
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
            )

        except ValueError:

            await update.message.reply_text(

                "❌ Summani faqat raqam bilan yozing.\n\n"
                "Masalan: 50000"
            )

            return

        if amount < MIN_WITHDRAW:

            await update.message.reply_text(

                f"❌ Minimal summa "
                f"{MIN_WITHDRAW:,} so'm."
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
            (user_id,)
        )

        row = cur.fetchone()

        if not row or row["balance"] < amount:

            conn.rollback()

            cur.close()

            conn.close()

            await update.message.reply_text(
                "❌ Balansingizda yetarli mablag' yo'q."
            )

            return

        context.user_data["withdraw_amount"] = amount

        context.user_data["mode"] = "withdraw_card"

        cur.close()

        conn.close()

        await update.message.reply_text(
            "💳 Karta raqamingizni yuboring:"
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

            context.user_data.pop(
                "mode",
                None
            )

            await update.message.reply_text(
                "❌ Jarayon tugadi. Qaytadan urinib ko'ring."
            )

            return

        card = text.strip()

        if len(card) < 8:

            await update.message.reply_text(
                "❌ Karta raqami noto'g'ri."
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
                (user_id,)
            )

            user_row = cur.fetchone()

            if not user_row or user_row["balance"] < amount:

                conn.rollback()

                await update.message.reply_text(
                    "❌ Balansingizda yetarli mablag' yo'q."
                )

                return

            cur.execute(
                """
                UPDATE users
                SET balance = balance - %s,
                    reserved_balance =
                        reserved_balance + %s
                WHERE id = %s
                """,
                (
                    amount,
                    amount,
                    user_id
                )
            )

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
                    card
                )
            )

            withdrawal = cur.fetchone()

            conn.commit()

            withdrawal_id = withdrawal["id"]

            context.user_data.pop(
                "mode",
                None
            )

            context.user_data.pop(
                "withdraw_amount",
                None
            )

            admin_text = (

                "💳 Yangi pul yechish so'rovi!\n\n"

                f"👤 Ism: {user.first_name}\n"

                f"🆔 ID: {user_id}\n"

                f"🔗 Username: "
                f"@{user.username if user.username else 'yo‘q'}\n\n"

                f"💰 Summa: {amount:,} so'm\n"

                f"💳 Karta: {card}"
            )

            await send_to_admins(

                context,

                admin_text,

                reply_markup=withdrawal_menu(
                    withdrawal_id
                )
            )

            await update.message.reply_text(

                "✅ Pul yechish so'rovingiz yuborildi.\n\n"

                f"💰 Summa: {amount:,} so'm\n"

                f"💳 Karta: {card}\n\n"

                "Admin tekshirganidan keyin "
                "pul o'tkaziladi."
            )

        except Exception as e:

            conn.rollback()

            logger.exception(
                "Withdrawal create xatosi"
            )

            await update.message.reply_text(
                "❌ Xatolik yuz berdi."
            )

        finally:

            cur.close()

            conn.close()

        return


# =========================================================
# VIDEO HANDLER
# =========================================================

async def handle_video(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    add_or_update_user(user)

    mode = context.user_data.get("mode")

    if mode != "video":

        await update.message.reply_text(

            "❌ Avval "
            "'🎥 Video sotaman' "
            "bo'limini tanlang."
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

    else:

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
            caption
        )
    )

    submission = cur.fetchone()

    conn.commit()

    cur.close()

    conn.close()

    submission_id = submission["id"]

    admin_caption = (

        "🎥 Yangi video!\n\n"

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
        "💰 Mukofotni tanlang:"
    )

    sent = await send_media_to_admins(

        context=context,

        file_id=file_id,

        caption=admin_caption,

        reply_markup=video_reward_menu(
            submission_id
        ),

        is_video=is_video
    )

    if not sent:

        conn = get_db()

        cur = conn.cursor()

        cur.execute(
            """
            UPDATE video_submissions
            SET status = 'rejected'
            WHERE id = %s
            """,
            (submission_id,)
        )

        conn.commit()

        cur.close()

        conn.close()

        await update.message.reply_text(

            "❌ Videoni adminlarga "
            "yuborishda xatolik yuz berdi."
        )

        return

    context.user_data.pop(
        "mode",
        None
    )

    await update.message.reply_text(

        "✅ Videongiz qabul qilindi.\n\n"

        "Adminlar tekshirganidan keyin "
        "mukofot balansingizga qo'shiladi."
    )


# =========================================================
# USERS COMMAND
# =========================================================

async def users_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        await update.message.reply_text(
            "❌ Sizda admin huquqi yo'q."
        )

        return

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COALESCE(SUM(balance), 0) AS balance,
            COALESCE(SUM(reserved_balance), 0) AS reserved
        FROM users
    """)

    row = cur.fetchone()

    cur.close()

    conn.close()

    await update.message.reply_text(

        "👥 STATISTIKA\n\n"

        f"👤 Foydalanuvchilar: {row['total']}\n"

        f"💰 Balanslar: {row['balance']:,} so'm\n"

        f"🔒 Rezerv: {row['reserved']:,} so'm"
    )


# =========================================================
# WITHDRAWALS COMMAND
# =========================================================

async def withdrawals_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        await update.message.reply_text(
            "❌ Sizda admin huquqi yo'q."
        )

        return

    await send_pending_withdrawals(
        update.message,
        context
    )


# =========================================================
# SEND PENDING WITHDRAWALS
# =========================================================

async def send_pending_withdrawals(
    message,
    context
):

    conn = get_db()

    cur = conn.cursor()

    cur.execute("""
        SELECT
            w.*,
            u.username,
            u.first_name
        FROM withdrawals w
        LEFT JOIN users u
            ON u.id = w.user_id
        WHERE w.status = 'pending'
        ORDER BY w.created_at ASC
    """)

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

            f"💰 Summa: {row['amount']:,} so'm\n"

            f"💳 Karta: {row['card']}"
        )

        await message.reply_text(

            text,

            reply_markup=withdrawal_menu(
                row["id"]
            )
        )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.exception(
        "Botda xatolik yuz berdi:",
        exc_info=context.error
    )


# =========================================================
# MAIN
# =========================================================

def main():

    init_db()

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
            start_command
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command
        )
    )

    application.add_handler(
        CommandHandler(
            "users",
            users_command
        )
    )

    application.add_handler(
        CommandHandler(
            "withdrawals",
            withdrawals_command
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
    # VIDEO
    # =====================================================

    application.add_handler(
        MessageHandler(
            filters.VIDEO | filters.Document.ALL,
            handle_video
        )
    )

    # =====================================================
    # TEXT
    # =====================================================

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    # =====================================================
    # ERROR
    # =====================================================

    application.add_error_handler(
        error_handler
    )

    # =====================================================
    # START LOG
    # =====================================================

    print("====================================")
    print("Navoiyliklar.uz Bot ishga tushdi")
    print("====================================")
    print("Adminlar:")
    print(" - 7267416938")
    print(" - 1058849364")
    print(" - 6820475808")
    print("====================================")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()