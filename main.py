
#!/usr/bin/env python3

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

# ================= CONFIG =================

BOT_TOKEN = os.getenv("MY_BOT_TOKEN")
OWNER_ID = 6435499094   # your Telegram user ID
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN not set.")

# ---------------- AUTO QUIZ SETTINGS ----------------

settings = {
    "interval": 60  # auto quiz interval in minutes
}

# ================= LOGGING =================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= HELPERS =================

def is_private(update: Update) -> bool:
    return update.effective_chat.type == Chat.PRIVATE


def is_group(update: Update) -> bool:
    return update.effective_chat.type in (Chat.GROUP, Chat.SUPERGROUP)


async def send_safe(update: Update, text: str):
    """Safely send message (avoids crashes)."""
    try:
        await update.message.reply_text(text)
    except Exception as e:
        logger.warning(f"Send failed: {e}")


# ================= PERMISSION DECORATORS =================

def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER_ID:
            await send_safe(update, "❌ Owner only command.")
            return
        return await func(update, context)
    return wrapper


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not db.is_admin(user_id):
            await send_safe(update, "❌ Admin only command.")
            return
        return await func(update, context)
    return wrapper


def group_admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_group(update):
            await send_safe(update, "❌ Group only command.")
            return

        member = await context.bot.get_chat_member(
            update.effective_chat.id,
            update.effective_user.id
        )

        if member.status not in ("administrator", "creator"):
            await send_safe(update, "❌ Group admins only.")
            return

        return await func(update, context)
    return wrapper

# ---------------- BASIC COMMANDS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == Chat.PRIVATE:
        db.add_user(user.id, user.username, user.first_name)
        await update.message.reply_text(
            f"Hello {user.first_name} 👋\nI am NEETIQBot 🤖\n\nType /help to see commands."
        )
    else:
        db.add_group(chat.id, chat.title, chat.type)
        await update.message.reply_text(
            "🎉 Group successfully registered with NEETIQBot!"
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *NEETIQBot Help*\n\n"
        "/randomquiz – Get a quiz\n"
        "/leaderboard – Global leaderboard\n"
        "/groupleaderboard – Group leaderboard\n"
        "/mystats – Your stats\n"
        "/questions – Question stats\n\n"
        "Admin:\n"
        "/addquestion\n"
        "/addcompliment\n"
        "/listcompliments\n"
        "/delcompliment\n"
        "/delallquestions\n"
        "/broadcast\n",
        parse_mode="Markdown"
    )


# ---------------- ADMIN CHECK ----------------

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_admin(user_id: int) -> bool:
    return db.is_admin(user_id) or is_owner(user_id)


# ---------------- ADMIN COMMANDS ----------------

async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /addadmin user_id")
        return

    user_id = int(context.args[0])
    db.add_admin(user_id)
    await update.message.reply_text(f"✅ User `{user_id}` added as admin.", parse_mode="Markdown")


async def removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /removeadmin user_id")
        return

    user_id = int(context.args[0])
    db.remove_admin(user_id)
    await update.message.reply_text(f"❌ User `{user_id}` removed from admin.", parse_mode="Markdown")


async def adminlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = db.get_admins()
    if not admins:
        await update.message.reply_text("No admins found.")
        return

    text = "👮 *Admin List*\n\n"
    for a in admins:
        text += f"• `{a}`\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# ---------------- BROADCAST ----------------

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    if not context.args:
        await update.message.reply_text("Usage:\n/broadcast Your message here")
        return

    message = " ".join(context.args)
    users = db.get_all_users()
    groups = db.get_all_groups()

    sent_u = failed_u = sent_g = failed_g = 0

    for u in users:
        try:
            await context.bot.send_message(u, message)
            sent_u += 1
        except:
            failed_u += 1

    for g in groups:
        try:
            await context.bot.send_message(g, message)
            sent_g += 1
        except:
            failed_g += 1

    await update.message.reply_text(
        f"📢 Broadcast Report\n\n"
        f"👤 Users:\n✅ Sent: {sent_u}\n❌ Failed: {failed_u}\n\n"
        f"👥 Groups:\n✅ Sent: {sent_g}\n❌ Failed: {failed_g}"
    )


# ---------------- BOT STATS ----------------

async def botstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db.count_users()
    groups = db.count_groups()
    questions = db.count_questions()
    attempted = db.count_attempted_users()

    await update.message.reply_text(
        "🤖 *Bot Statistics*\n\n"
        f"👤 Total Users: {users}\n"
        f"👥 Total Groups: {groups}\n"
        f"📘 Total Questions: {questions}\n"
        f"🧠 Users Attempted Quiz: {attempted}",
        parse_mode="Markdown"
    )
# ---------------- QUESTIONS ----------------

async def addquestion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    text = update.message.text
    lines = text.split("\n")

    added = 0
    skipped = 0
    i = 1

    while i < len(lines):
        try:
            question = lines[i].strip()
            options = [lines[i+1], lines[i+2], lines[i+3], lines[i+4]]
            correct = int(lines[i+5].strip())
            explanation = lines[i+6].strip()

            if correct not in [1, 2, 3, 4]:
                skipped += 1
                i += 7
                continue

            db.add_question(
                question=question,
                options=options,
                correct=correct,
                explanation=explanation
            )
            added += 1
            i += 7

        except Exception:
            skipped += 1
            i += 1

    await update.message.reply_text(
        f"✅ {added} questions added successfully.\n"
        f"⚠️ {skipped} questions skipped (invalid format)."
    )


async def delallquestions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    db.delete_all_questions()
    await update.message.reply_text("🗑️ All questions deleted successfully.")


async def questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = db.count_questions()
    attempted = db.count_attempted_questions()
    left = total - attempted

    await update.message.reply_text(
        "📘 *Question Statistics*\n\n"
        f"📦 Total Questions: {total}\n"
        f"📂 Questions Left: {left}\n"
        f"✅ Questions Attempted: {attempted}",
        parse_mode="Markdown"
    )

# ---------------- QUIZ CORE ----------------

async def randomquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        await update.message.reply_text("⚠️ Use this command in a group.")
        return

    question = db.get_random_question(chat.id)
    if not question:
        await update.message.reply_text(
            "⚠️ No questions available right now.\nAdmins have been notified."
        )
        return

    q_id, q_text, options, correct = question

    poll_msg = await context.bot.send_poll(
        chat_id=chat.id,
        question=q_text,
        options=options,
        is_anonymous=False,
        type=Poll.QUIZ,
        correct_option_id=correct - 1
    )

    db.register_poll(
        poll_id=poll_msg.poll.id,
        question_id=q_id,
        chat_id=chat.id
    )


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    user = answer.user

    poll_data = db.get_poll(answer.poll_id)
    if not poll_data:
        return

    question_id, correct_option, chat_id = poll_data
    selected = answer.option_ids[0]

    is_correct = selected == (correct_option - 1)

    db.record_attempt(
        user_id=user.id,
        chat_id=chat_id,
        question_id=question_id,
        correct=is_correct
    )
   # -------- GROUP STATS UPDATE --------
db.update_group_stats(
    chat_id=chat_id,
    user_id=user.id,
    correct=is_correct
)


    # -------- STREAK LOGIC --------
    if is_correct:
        db.increment_streak(user.id)
    else:
        db.reset_streak(user.id)

    # -------- COMPLIMENTS --------
    if not db.is_compliments_off(chat_id):
        compliment = db.get_compliment(is_correct)
        if compliment:
            text = compliment.replace("{user}", user.first_name)
            await context.bot.send_message(chat_id, text)

# ---------------- COMPLIMENTS ----------------

@admin_only
async def addcompliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n/addcompliment correct Your text {user}\n"
            "/addcompliment wrong Your text {user}"
        )
        return

    ctype = context.args[0].lower()
    text = " ".join(context.args[1:])

    if ctype not in ("correct", "wrong"):
        await update.message.reply_text("❌ Type must be `correct` or `wrong`.")
        return

    db.add_compliment(ctype, text)
    await update.message.reply_text("✅ Compliment added successfully.")


@admin_only
async def delcompliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /delcompliment compliment_id")
        return

    try:
        cid = int(context.args[0])
        db.delete_compliment(cid)
        await update.message.reply_text("🗑️ Compliment deleted.")
    except:
        await update.message.reply_text("❌ Invalid compliment ID.")


@admin_only
async def listcompliments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.list_compliments()

    if not rows:
        await update.message.reply_text("⚠️ No compliments found.")
        return

    text = "💬 *Compliments List*\n\n"
    for r in rows:
        text += f"ID `{r['id']}` | {r['type']} → {r['text']}\n"

    await update.message.reply_text(text, parse_mode="Markdown")


@group_admin_only
async def offcompliments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db.set_compliments_off(chat_id)
    await update.message.reply_text("🔕 Compliments turned OFF in this group.")

# ---------------- AUTO QUIZ ----------------

@group_admin_only
async def autoquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.enable_autoquiz(update.effective_chat.id)
    await update.message.reply_text("⏱️ Auto quiz enabled for this group.")


async def auto_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    groups = db.get_autoquiz_groups()
    for gid in groups:
        try:
            question = db.get_random_question(gid)
            if not question:
                continue

            q_id, q_text, options, correct = question
            poll = await context.bot.send_poll(
                chat_id=gid,
                question=q_text,
                options=options,
                is_anonymous=False,
                type=Poll.QUIZ,
                correct_option_id=correct - 1
            )

            db.register_poll(poll.poll.id, q_id, gid)
        except Exception as e:
            logger.warning(f"Autoquiz failed in {gid}: {e}")


async def nightly_leaderboard_job(context: ContextTypes.DEFAULT_TYPE):
    groups = db.get_all_groups()
    for gid in groups:
        try:
            rows = db.get_group_leaderboard(gid, limit=10)
            if not rows:
                continue

            text = "🌙 *Nightly Group Leaderboard*\n\n"
            for i, r in enumerate(rows, 1):
                text += f"{i}. {r['name']} — {r['score']}\n"

            await context.bot.send_message(gid, text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Nightly leaderboard failed in {gid}: {e}")

# ---------------- LEADERBOARDS ----------------

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_global_leaderboard(limit=25)

    if not rows:
        await update.message.reply_text("📭 No leaderboard data yet.")
        return

    text = "🌍 Global Leaderboard (Top 25)\n\n"
    for i, row in enumerate(rows, start=1):
        text += (
            f"🥇 {row['name']}\n"
            f"📘 Attempted: {row['attempted']} | "
            f"✅ Correct: {row['correct']} | "
            f"🏆 Score: {row['score']}\n\n"
        )

    await update.message.reply_text(text)


async def groupleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if chat.type not in [Chat.GROUP, Chat.SUPERGROUP]:
        await update.message.reply_text("⚠️ Use this command in a group.")
        return

    rows = db.get_group_leaderboard(chat.id, limit=25)
    if not rows:
        await update.message.reply_text("📭 No group leaderboard data yet.")
        return

    text = "👥 Group Leaderboard (Top 25)\n\n"
    for i, row in enumerate(rows, start=1):
        text += (
            f"🥇 {row['name']}\n"
            f"📘 Attempted: {row['attempted']} | "
            f"✅ Correct: {row['correct']} | "
            f"🏆 Score: {row['score']}\n\n"
        )

    await update.message.reply_text(text)


# ---------------- USER STATS ----------------

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = db.get_user_stats(user.id)

    if not stats:
        await update.message.reply_text("📊 No stats yet. Start playing quizzes!")
        return

    accuracy = (
        (stats["correct"] / stats["attempted"]) * 100
        if stats["attempted"] else 0
    )

    text = (
        "📊 Your Stats\n\n"
        f"📘 Attempts: {stats['attempted']}\n"
        f"✅ Correct: {stats['correct']}\n"
        f"❌ Wrong: {stats['wrong']}\n"
        f"🎯 Accuracy: {accuracy:.2f}%\n\n"
        f"🔥 Best Streak: {stats['best_streak']}\n"
        f"🌞 Daily Streak: {stats['daily_streak']}\n"
        f"🏆 Max Streak: {stats['max_streak']}\n\n"
        f"🏆 Score: {stats['score']}"
    )

    await update.message.reply_text(text)


# ---------------- BOT STATS ----------------

async def botstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_bot_stats()

    text = (
        "🤖 Bot Statistics\n\n"
        f"👤 Total Users: {stats['users']}\n"
        f"👥 Total Groups: {stats['groups']}\n"
        f"📘 Total Questions: {stats['questions']}\n"
        f"🧠 Users Attempted Quiz: {stats['attempted_users']}"
    )

    await update.message.reply_text(text)
    def main():
    db.init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # BASIC
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    # ADMIN
    app.add_handler(CommandHandler("addadmin", addadmin))
    app.add_handler(CommandHandler("removeadmin", removeadmin))
    app.add_handler(CommandHandler("adminlist", adminlist))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("botstats", botstats))

    # QUESTIONS & QUIZ
    app.add_handler(CommandHandler("addquestion", addquestion))
    app.add_handler(CommandHandler("delallquestions", delallquestions))
    app.add_handler(CommandHandler("questions", questions))
    app.add_handler(CommandHandler("randomquiz", randomquiz))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    # LEADERBOARDS & STATS
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("groupleaderboard", groupleaderboard))
    app.add_handler(CommandHandler("mystats", mystats))

    # COMPLIMENTS
    app.add_handler(CommandHandler("addcompliment", addcompliment))
    app.add_handler(CommandHandler("delcompliment", delcompliment))
    app.add_handler(CommandHandler("listcompliments", listcompliments))
    app.add_handler(CommandHandler("offcompliments", offcompliments))

    # AUTO QUIZ
    app.add_handler(CommandHandler("autoquiz", autoquiz))

    app.job_queue.run_repeating(
        auto_quiz_job,
        interval=settings["interval"] * 60,
        first=20
    )

    app.job_queue.run_daily(
        nightly_leaderboard_job,
        time=time(hour=21, minute=0)
    )

    logger.info("🤖 NEETIQBot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

