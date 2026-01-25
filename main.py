#!/usr/bin/env python3

# =========================
# IMPORTS
# =========================
import logging
import os
from datetime import datetime, time, timedelta

from telegram import (
    Update,
    Poll,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Chat,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    PollAnswerHandler,
)

import database as db

# =========================
# CONFIG
# =========================
BOT_TOKEN = os.getenv("MY_BOT_TOKEN")   # Railway environment variable
OWNER_ID = 6435499094                  # Your Telegram user ID

# =========================
# LOGGING
# =========================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================
# CONSTANTS
# =========================
STREAK_MILESTONES = {3, 5, 10}
TELEGRAM_MESSAGE_LIMIT = 3900  # safe limit

# =========================
# HELPERS
# =========================
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def chunk_text(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT):
    """
    Split long text into Telegram-safe chunks
    """
    chunks = []
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:]
    chunks.append(text)
    return chunks


def apply_footer(text: str) -> str:
    return f"{text}\n\n━━━━━━━━━━━━━━━\nNEETIQBot"


def rank_badge(rank: int) -> str:
    if rank == 1:
        return "🥇"
    elif rank == 2:
        return "🥈"
    elif rank == 3:
        return "🥉"
    return f"{rank}."


def today_date() -> str:
    return datetime.utcnow().date().isoformat()


def current_week_range():
    today = datetime.utcnow().date()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()

# =========================
# BASIC COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    db.add_chat(
        chat_id=chat.id,
        chat_type=chat.type,
        title=chat.title
    )

    text = (
        "👋 *Welcome to NEETIQBot!*\n\n"
        "🧠 Daily NEET-level MCQs\n"
        "🏆 Leaderboards & streaks\n"
        "📊 Detailed stats tracking\n\n"
        "Use /help to see all commands."
    )

    await update.message.reply_text(
        apply_footer(text),
        parse_mode="Markdown"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📌 *Available Commands*\n\n"
        "/randomquiz – Get a quiz\n"
        "/autoquiz – Toggle auto quiz\n"
        "/questions – Question stats\n"
        "/leaderboard – Global leaderboard\n"
        "/groupleaderboard – Group leaderboard\n"
        "/mystats – Your detailed stats\n\n"
        "👮 Admin:\n"
        "/addquestion\n"
        "/delallquestions\n"
        "/addcompliment\n"
        "/delcompliment\n"
        "/listcompliments\n"
        "/offcompliments\n"
        "/botstats"
    )

    await update.message.reply_text(
        apply_footer(text),
        parse_mode="Markdown"
  )
# =========================
# ADMIN HELPERS
# =========================
def is_admin(user_id: int) -> bool:
    return db.is_admin(user_id)


def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not is_admin(user.id) and not is_owner(user.id):
            await update.message.reply_text("❌ Admin only command.")
            return
        return await func(update, context)
    return wrapper


# =========================
# ADMIN COMMANDS
# =========================
@require_admin
async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return

    user_id = int(context.args[0])
    db.add_admin(user_id)
    await update.message.reply_text(f"✅ User `{user_id}` added as admin.", parse_mode="Markdown")


@require_admin
async def removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /removeadmin <user_id>")
        return

    user_id = int(context.args[0])
    db.remove_admin(user_id)
    await update.message.reply_text(f"✅ Admin `{user_id}` removed.", parse_mode="Markdown")


@require_admin
async def adminlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = db.get_admins()
    if not admins:
        await update.message.reply_text("No admins found.")
        return

    text = "👮 *Admins List*\n\n"
    for a in admins:
        text += f"• `{a['user_id']}`\n"

    await update.message.reply_text(
        apply_footer(text),
        parse_mode="Markdown"
    )


# =========================
# COMPLIMENTS SYSTEM
# =========================
@require_admin
async def addcompliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addcompliment <correct|wrong> <text>")
        return

    ctype = context.args[0].lower()
    text = " ".join(context.args[1:])

    if ctype not in ("correct", "wrong"):
        await update.message.reply_text("Type must be `correct` or `wrong`.")
        return

    db.add_compliment(ctype, text)
    await update.message.reply_text("✅ Compliment added.")


@require_admin
async def delcompliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /delcompliment <id>")
        return

    cid = int(context.args[0])
    db.delete_compliment(cid)
    await update.message.reply_text("🗑 Compliment deleted.")


async def listcompliments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_all_compliments()
    if not rows:
        await update.message.reply_text("No compliments found.")
        return

    text = "💬 *Compliments List*\n\n"
    for r in rows:
        text += f"#{r['id']} [{r['type']}]\n{r['text']}\n\n"

    for chunk in chunk_text(text):
        await update.message.reply_text(
            apply_footer(chunk),
            parse_mode="Markdown"
        )


# =========================
# GROUP COMPLIMENT TOGGLE
# =========================
async def offcompliments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == Chat.PRIVATE:
        await update.message.reply_text("❌ Group-only command.")
        return

    admins = await context.bot.get_chat_administrators(chat.id)
    admin_ids = [a.user.id for a in admins]

    if user.id not in admin_ids:
        await update.message.reply_text("❌ Only group admins can do this.")
        return

    db.set_compliments_enabled(chat.id, False)
    await update.message.reply_text("🔕 Compliments turned OFF for this group.")


async def oncompliments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == Chat.PRIVATE:
        await update.message.reply_text("❌ Group-only command.")
        return

    admins = await context.bot.get_chat_administrators(chat.id)
    admin_ids = [a.user.id for a in admins]

    if user.id not in admin_ids:
        await update.message.reply_text("❌ Only group admins can do this.")
        return

    db.set_compliments_enabled(chat.id, True)
    await update.message.reply_text("🔔 Compliments turned ON for this group.")

# =========================
# QUIZ COMMAND
# =========================
async def randomquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    q = db.get_random_question(chat.id)

    if not q:
        await update.message.reply_text("⚠️ No questions available.")
        return

    options = [q["a"], q["b"], q["c"], q["d"]]
    correct_index = ord(q["correct"]) - ord("A")

    msg = await context.bot.send_poll(
        chat_id=chat.id,
        question=q["question"],
        options=options,
        type=Poll.QUIZ,
        correct_option_id=correct_index,
        is_anonymous=False,
        explanation=q["explanation"] or None
    )

    context.bot_data[msg.poll.id] = {
        "question_id": q["id"],
        "correct_index": correct_index,
        "chat_id": chat.id
    }


# =========================
# POLL ANSWER HANDLER
# =========================
async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    user = answer.user
    poll_data = context.bot_data.get(answer.poll_id)

    if not poll_data:
        return

    chosen = answer.option_ids[0]
    is_correct = chosen == poll_data["correct_index"]
    chat_id = poll_data["chat_id"]

    # Save user always
    db.add_user(user.id, user.username, user.first_name)

    # Update stats (GLOBAL)
    db.update_user_stats(
        user_id=user.id,
        is_correct=is_correct
    )

    # Update GROUP stats
    if chat_id < 0:
        db.update_group_stats(
            chat_id=chat_id,
            user_id=user.id,
            name=user.username or user.first_name,
            is_correct=is_correct
        )

    # Compliments (group only + enabled)
    if chat_id < 0 and db.are_compliments_enabled(chat_id):
        compliment = db.get_random_compliment("correct" if is_correct else "wrong")
        if compliment:
            name = f"@{user.username}" if user.username else user.first_name
            text = compliment.replace("{user}", name)
            try:
                await context.bot.send_message(chat_id, text)
            except:
                pass


# =========================
# USER STATS
# =========================
async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = db.get_user_stats(user.id)

    if not stats:
        await update.message.reply_text("No stats yet.")
        return

    accuracy = (
        (stats["correct"] / stats["attempted"]) * 100
        if stats["attempted"] > 0 else 0
    )

    text = (
        "📊 *Your Stats*\n\n"
        f"📘 Attempts: {stats['attempted']}\n"
        f"✅ Correct: {stats['correct']}\n"
        f"❌ Wrong: {stats['incorrect']}\n"
        f"🎯 Accuracy: {accuracy:.2f}%\n\n"
        f"🔥 Best Streak: {stats['best_streak']}\n"
        f"🌞 Daily Streak: {stats['daily_streak']}\n"
        f"🏆 Max Streak: {stats['max_streak']}\n\n"
        f"📅 Weekly Correct: {stats['weekly_correct']}\n\n"
        f"🏆 Score: {stats['score']}"
    )

    await update.message.reply_text(
        apply_footer(text),
        parse_mode="Markdown"
    )


# =========================
# GLOBAL LEADERBOARD
# =========================
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_global_leaderboard(limit=10)
    if not rows:
        await update.message.reply_text("No data.")
        return

    text = "🌍 *Global Leaderboard*\n\n"
    for i, r in enumerate(rows, 1):
        name = r["first_name"] or r["username"] or r["user_id"]
        text += f"{i}. {name} — {r['score']}\n"

    await update.message.reply_text(
        apply_footer(text),
        parse_mode="Markdown"
    )


# =========================
# GROUP LEADERBOARD
# =========================
async def groupleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == Chat.PRIVATE:
        await update.message.reply_text("❌ Group only.")
        return

    rows = db.get_group_leaderboard(chat.id, limit=10)
    if not rows:
        await update.message.reply_text("No data.")
        return

    text = f"👥 *{chat.title} Leaderboard*\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. {r['name']} — {r['score']}\n"

    await update.message.reply_text(
        apply_footer(text),
        parse_mode="Markdown"
    )


# =========================
# QUESTIONS LIST (PAGINATED)
# =========================
async def questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_all_questions()
    if not rows:
        await update.message.reply_text("No questions found.")
        return

    text = "📚 *Questions*\n\n"
    for q in rows:
        text += f"{q['id']}. {q['question']}\n\n"

    for chunk in chunk_text(text):
        await update.message.reply_text(
            apply_footer(chunk),
            parse_mode="Markdown"
        )


# =========================
# DELETE ALL QUESTIONS
# =========================
@require_admin
async def delallquestions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.delete_all_questions()
    await update.message.reply_text("🗑 All questions deleted.")
# =========================
# ADD QUESTION
# =========================
@require_admin
async def addquestion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = update.message.text.split("\n")

    if len(lines) < 8:
        await update.message.reply_text(
            "❌ Invalid format.\n\n"
            "/addquestion\n"
            "Question\nA\nB\nC\nD\nCorrect(1-4)\nExplanation"
        )
        return

    try:
        question = lines[1].strip()
        a, b, c, d = [x.strip() for x in lines[2:6]]
        correct = ["A", "B", "C", "D"][int(lines[6].strip()) - 1]
        explanation = lines[7].strip()

        db.add_question(question, a, b, c, d, correct, explanation)
        await update.message.reply_text("✅ Question added successfully")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# =========================
# DELETE ALL QUESTIONS
# =========================
@require_admin
async def delallquestions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.delete_all_questions()
    await update.message.reply_text("🗑 All questions deleted")




# =========================
# AUTO QUIZ
# =========================
async def autoquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    minutes = int(context.args[0])
    db.set_autoquiz(minutes)
    await update.message.reply_text(f"⏱ Auto quiz every {minutes} minutes")


async def auto_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    chats = db.get_active_chats()
    for chat_id in chats:
        q = db.get_random_question(chat_id)
        if not q:
            continue

        options = [q["a"], q["b"], q["c"], q["d"]]
        correct_index = ord(q["correct"]) - ord("A")

        msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=q["question"],
            options=options,
            type=Poll.QUIZ,
            correct_option_id=correct_index,
            is_anonymous=False
        )

        context.bot_data[msg.poll.id] = {
            "question_id": q["id"],
            "correct_index": correct_index,
            "chat_id": chat_id
      }
      
  # =========================
# BOT STATS
# =========================
@require_owner
async def botstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_bot_stats()
    text = (
        "🤖 Bot Stats\n\n"
        f"👥 Users: {stats['users']}\n"
        f"💬 Groups: {stats['groups']}\n"
        f"📚 Questions: {stats['questions']}\n"
        f"🧠 Attempts: {stats['attempts']}"
    )
    await update.message.reply_text(text)


# =========================
# MAIN (FINAL)
# =========================
def main():
    db.init_db()

    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN not set")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # BASIC
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    # QUIZ
    app.add_handler(CommandHandler("addquestion", addquestion))
    app.add_handler(CommandHandler("randomquiz", randomquiz))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    # STATS
    app.add_handler(CommandHandler("mystats", mystats))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("groupleaderboard", groupleaderboard))
    app.add_handler(CommandHandler("questions", questions))
    app.add_handler(CommandHandler("delallquestions", delallquestions))

    # COMPLIMENTS
    app.add_handler(CommandHandler("addcompliment", addcompliment))
    app.add_handler(CommandHandler("delcompliment", delcompliment))
    app.add_handler(CommandHandler("listcompliments", listcompliments))
    app.add_handler(CommandHandler("offcompliments", offcompliments))

    # AUTO QUIZ
    app.add_handler(CommandHandler("autoquiz", autoquiz))

    # BOT
    app.add_handler(CommandHandler("botstats", botstats))

    app.run_polling()


if __name__ == "__main__":
    main()
