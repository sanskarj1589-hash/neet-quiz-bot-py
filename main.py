import os
import logging
from datetime import datetime, timedelta

from telegram import (
    Update,
    Poll,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Chat
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    PollAnswerHandler
)

import database as db

# ================= LOGGING =================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

# ================= APP =================

app = Application.builder().token(BOT_TOKEN).build()

# ================= BASIC COMMANDS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if user:
        db.add_or_update_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

    if chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        db.add_or_update_group(chat.id, chat.title)

        await update.message.reply_text(
            "👋 Bot activated!\n\n"
            "I’ll send quizzes here.\n"
            "Use /help to see commands."
        )
    else:
        await update.message.reply_text(
            "👋 Welcome to NEETIQ Bot!\n\n"
            "Add me to a group and make me admin to start quizzes.\n"
            "Use /help to see commands."
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Available Commands:\n\n"
        "/start – Activate bot\n"
        "/quiz – Send a quiz\n"
        "/autoquiz on <minutes> – Enable auto quiz\n"
        "/autoquiz off – Disable auto quiz\n"
        "/leaderboard – Group leaderboard\n"
        "/gleaderboard – Global leaderboard\n"
        "/stats – Bot statistics\n"
        "/ping – Check bot status"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Bot is alive.")


# ================= HANDLER REGISTRATION =================

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CommandHandler("ping", ping))

# ================= QUIZ LOGIC =================

async def send_quiz(chat_id, context: ContextTypes.DEFAULT_TYPE):
    question = db.get_random_question(chat_id)
    if not question:
        db.clear_sent_questions(chat_id)
        question = db.get_random_question(chat_id)
        if not question:
            return

    poll_message = await context.bot.send_poll(
        chat_id=chat_id,
        question=question["question"],
        options=question["options"],
        type=Poll.QUIZ,
        correct_option_id=question["correct_option"],
        explanation=question["explanation"] or "",
        is_anonymous=False
    )

    context.bot_data[poll_message.poll.id] = {
        "question_id": question["id"],
        "chat_id": chat_id,
        "correct_option": question["correct_option"]
    }

    db.mark_question_sent(question["id"], chat_id)
    db.update_last_autoquiz(chat_id)


async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        await update.message.reply_text("Quiz works only in groups.")
        return

    await send_quiz(chat.id, context)


async def autoquiz_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        return

    group = db.get_group(chat.id)
    if not group or not group["autoquiz_enabled"]:
        return

    last = group["last_autoquiz_time"]
    interval = timedelta(minutes=group["autoquiz_interval"])

    if last and datetime.utcnow() - last < interval:
        return

    await send_quiz(chat.id, context)


# ================= HANDLER =================

app.add_handler(CommandHandler("quiz", quiz_cmd))

# ================= POLL ANSWERS =================

async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    user = answer.user
    poll_id = answer.poll_id

    if poll_id not in context.bot_data:
        return

    data = context.bot_data[poll_id]
    chat_id = data["chat_id"]
    correct_option = data["correct_option"]

    selected = answer.option_ids[0]
    is_correct = selected == correct_option

    # register user
    db.add_or_update_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    if is_correct:
        db.update_user_score(user.id, 4)
        db.update_group_score(chat_id, user.id, 4)
        db.update_streaks(user.id, True)

        compliment = db.get_random_compliment()
        text = f"✅ Correct! +4 points\n\n{compliment}"
    else:
        db.update_user_score(user.id, -1)
        db.update_group_score(chat_id, user.id, -1)
        db.update_streaks(user.id, False)

        text = "❌ Wrong! -1 point"

    await

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"👤 {user.first_name}\n{text}"
        )
    except Exception:
        pass


# ================= HANDLER =================

app.add_handler(PollAnswerHandler(poll_answer_handler))

# ================= AUTO QUIZ COMMAND =================

async def autoquiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        await update.message.reply_text("Auto quiz works only in groups.")
        return

    if not db.is_admin(user.id):
        await update.message.reply_text("Only admins can control auto quiz.")
        return

    if not context.args:
        await update.message.reply_text("Usage:\n/autoquiz on <minutes>\n/autoquiz off")
        return

    if context.args[0].lower() == "off":
        db.set_autoquiz(chat.id, False, 30)
        await update.message.reply_text("❌ Auto quiz disabled.")
        return

    if context.args[0].lower() == "on":
        try:
            minutes = int(context.args[1])
        except Exception:
            await update.message.reply_text("Please provide interval in minutes.")
            return

        db.set_autoquiz(chat.id, True, minutes)
        await update.message.reply_text(f"✅ Auto quiz enabled every {minutes} minutes.")


# ================= LEADERBOARDS =================

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    data = db.get_group_leaderboard(chat.id)

    if not data:
        await update.message.reply_text("No data yet.")
        return

    text = "🏆 Group Leaderboard\n\n"
    for i, row in enumerate(data, start=1):
        name = row["first_name"] or row["username"] or "User"
        text += f"{i}. {name} — {row['score']} pts\n"

    await update.message.reply_text(text)


async def global_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = db.get_global_leaderboard()

    if not data:
        await update.message.reply_text("No data yet.")
        return

    text = "🌍 Global Leaderboard\n\n"
    for i, row in enumerate(data, start=1):
        name = row["first_name"] or row["username"] or "User"
        text += f"{i}. {name} — {row['score']} pts\n"

    await update.message.reply_text(text)


# ================= STATS =================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = db.get_bot_stats()
    await update.message.reply_text(
        f"📊 Bot Stats\n\n"
        f"👥 Users: {s['users']}\n"
        f"👥 Groups: {s['groups']}\n"
        f"❓ Questions: {s['questions']}"
    )


# ================= HANDLERS =================

app.add_handler(CommandHandler("autoquiz", autoquiz_cmd))
app.add_handler(CommandHandler("leaderboard", leaderboard))
app.add_handler(CommandHandler("gleaderboard", global_leaderboard))
app.add_handler(CommandHandler("stats", stats))

# ================= AUTOQUIZ TRIGGER =================

from telegram.ext import MessageHandler, filters

async def on_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await autoquiz_check(update, context)

app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_any_message))


# ================= STARTUP =================

async def on_startup(app: Application):
    db.init_db()
    if WEBHOOK_URL:
        await app.bot.set_webhook(WEBHOOK_URL)
        logger.info("Webhook set")


def main():
    app.post_init = on_startup

    if WEBHOOK_URL:
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", 10000)),
            webhook_url=WEBHOOK_URL
        )
    else:
        app.run_polling()


if __name__ == "__main__":
    main()


