#!/usr/bin/env python3
import logging
import os

from datetime import time
from telegram import Poll
from telegram.ext import PollAnswerHandler
import database as db

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Chat
)
from telegram import Update, Poll
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    PollAnswerHandler,
)

import database as db

# ---------------- CONFIG ----------------
BOT_TOKEN = "8203396114:AAE_Ii9RuLvhCA64PRPwq1BZVc7bEPZmq0g"
OWNER_ID = 6435499094

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ---------------- HELPERS ----------------

def apply_footer(text: str) -> str:
    footer = db.get_footer()

    if not footer["enabled"]:
        return text

    if not footer["text"]:
        return text

    return f"{text}\n\n━━━━━━━━━━━━━━━\n{footer['text']}"

def build_group_leaderboard_text(chat_id: int, limit=10) -> str:
    board = db.get_group_leaderboard(chat_id, limit)

    if not board:
        return None

    text = "👥 *Group Leaderboard*\n\n"
    rank = 1

    for u in board:
        name = u["username"] or str(u["user_id"])
        text += f"{rank}. {name} — 🏆 {u['score']}\n"
        rank += 1

    return apply_footer(text)

def get_add_to_group_keyboard():
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "➕ Add me to your Group",
                url="https://t.me/NEETIQBot?startgroup=true"
            )
        ]]
    )


# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # Register user
    if user:
        db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )

    # Group behavior
    if chat and chat.type in (Chat.GROUP, Chat.SUPERGROUP):
        # Register group
        db.add_chat(
            chat_id=chat.id,
            chat_type=chat.type,
            title=chat.title
        )

        await update.message.reply_text(
            "🎉 Group successfully registered with NEETIQBot!"
        )
        logger.info(f"Group registered: {chat.id} | {chat.title}")
        return

    # Private chat welcome
    text = (
        f"Hello {user.first_name} 👋\n"
        "I am NEETIQBot 🤖\n\n"
        "Type /help to see available commands."
    )

    await update.message.reply_text(
        text,
        reply_markup=get_add_to_group_keyboard()
    )
    logger.info(f"User started bot: {user.id}")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Help\n\n"
        "Use /start to begin.\n"
        "More commands will appear soon."
    )

# ---------------- ADMIN / OWNER COMMANDS ----------------

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_owner(user.id):
        await update.message.reply_text("❌ Only owner can add admins.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addadmin <user_id>")
        return

    try:
        admin_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    db.add_admin(admin_id)
    await update.message.reply_text(f"✅ User `{admin_id}` added as admin.")


async def removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_owner(user.id):
        await update.message.reply_text("❌ Only owner can remove admins.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /removeadmin <user_id>")
        return

    try:
        admin_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    db.remove_admin(admin_id)
    await update.message.reply_text(f"✅ User `{admin_id}` removed from admins.")


async def adminlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_owner(user.id):
        await update.message.reply_text("❌ Only owner can view admin list.")
        return

    admins = db.list_admins()

    if not admins:
        await update.message.reply_text("ℹ️ No admins added yet.")
        return

    text = "👮 Admin List:\n\n"
    for a in admins:
        text += f"• `{a['user_id']}`\n"

    await update.message.reply_text(text)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    print("🔥 BROADCAST HANDLER STARTED")

    # ADMIN CHECK
    if not db.is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    # MESSAGE CHECK
    if not context.args:
        await update.message.reply_text(
            "Usage:\n/broadcast Your message here"
        )
        return

    message = " ".join(context.args)

    sent_users = failed_users = 0
    sent_groups = failed_groups = 0

async def footer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not db.is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    if not context.args:
        data = db.get_footer()
        status = "ON ✅" if data["enabled"] else "OFF ❌"
        text = data["text"] or "Not set"

        await update.message.reply_text(
            f"🧾 Footer Status: {status}\n\nText:\n{text}"
        )
        return

    arg = context.args[0].lower()

    if arg == "on":
        db.set_footer_enabled(True)
        await update.message.reply_text("✅ Footer enabled")

    elif arg == "off":
        db.set_footer_enabled(False)
        await update.message.reply_text("⛔ Footer disabled")

    else:
        footer_text = " ".join(context.args)
        db.set_footer_text(footer_text)
        await update.message.reply_text("✅ Footer text updated")

    # ================= USERS =================
    with db.get_db() as conn:
        users = conn.execute(
            "SELECT user_id FROM users"
        ).fetchall()

    for u in users:
        try:
            await context.bot.send_message(
                chat_id=int(u["user_id"]),
                text=message
            )
            sent_users += 1
        except Exception as e:
            failed_users += 1
            print(f"User broadcast failed {u['user_id']}: {e}")

    # ================= GROUPS =================
    groups = db.get_all_groups()
    print("📦 GROUP IDS:", groups)

    for chat_id in groups:
        try:
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=message
            )
            sent_groups += 1
        except Exception as e:
            failed_groups += 1
            print(f"Group broadcast failed {chat_id}: {e}")

    # ================= REPORT =================
    await update.message.reply_text(
        "📢 *Broadcast Report*\n\n"
        f"👤 Users:\n"
        f"✅ Sent: {sent_users}\n"
        f"❌ Failed: {failed_users}\n\n"
        f"👥 Groups:\n"
        f"✅ Sent: {sent_groups}\n"
        f"❌ Failed: {failed_groups}",
        parse_mode="Markdown"
    )

# ---------------- COMPLIMENT COMMANDS (ADMIN) ----------------

async def addcompliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not db.is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "/addcompliment correct Your text {user}\n"
            "/addcompliment wrong Your text {user}"
        )
        return

    ctype = context.args[0].lower()
    if ctype not in ("correct", "wrong"):
        await update.message.reply_text("❌ Type must be `correct` or `wrong`.")
        return

    text = " ".join(context.args[1:])

    db.add_compliment(ctype, text)
    await update.message.reply_text("✅ Compliment added successfully.")


async def listcompliments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not db.is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT type, text FROM compliments ORDER BY type"
        ).fetchall()

    if not rows:
        await update.message.reply_text("📭 No compliments added yet.")
        return

    text = "💬 *Compliments*\n\n"
    for r in rows:
        text += f"• ({r['type']}) {r['text']}\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# ---------------- ADD QUESTION (ADMIN ONLY | PRIVATE CHAT) ----------------
import re
from telegram import Chat

QUESTION_BLOCK_REGEX = re.compile(
    r"""
    ^\d+\.\s*(?P<question>.+?)\n
    A\.\s*(?P<A>.+?)\n
    B\.\s*(?P<B>.+?)\n
    C\.\s*(?P<C>.+?)\n
    D\.\s*(?P<D>.+?)\n
    (?P<answer>[1-4])\n?
    (?P<explanation>.*)?
    """,
    re.VERBOSE | re.DOTALL
)


def parse_questions(text: str):
    blocks = re.split(r"\n\s*\n", text.strip())
    valid = []
    skipped = 0

    for block in blocks:
        match = QUESTION_BLOCK_REGEX.match(block.strip())
        if not match:
            skipped += 1
            continue

        data = match.groupdict()
        correct = ["A", "B", "C", "D"][int(data["answer"]) - 1]

        valid.append({
            "question": data["question"].strip(),
            "a": data["A"].strip(),
            "b": data["B"].strip(),
            "c": data["C"].strip(),
            "d": data["D"].strip(),
            "correct": correct,
            "explanation": data["explanation"].strip() if data["explanation"] else None
        })

    return valid, skipped


async def addquestion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # Only admin
    if not db.is_admin(user.id):
        await update.message.reply_text("❌ You are not authorized.")
        return

    # Private chat only
    if chat.type != Chat.PRIVATE:
        await update.message.reply_text("❌ Please use this command in private chat.")
        return

    # Get content
    if update.message.text and update.message.text.startswith("/addquestion"):
        content = update.message.text.replace("/addquestion", "", 1).strip()

    elif update.message.document and update.message.document.file_name.endswith(".txt"):
        file = await update.message.document.get_file()
        data = await file.download_as_bytearray()
        content = data.decode("utf-8")

    else:
        await update.message.reply_text(
            "❌ Send questions as text or .txt file.\n\n"
            "Use the approved question format."
        )
        return

    questions, skipped = parse_questions(content)

    if not questions:
        await update.message.reply_text("❌ No valid questions found.")
        return

    for q in questions:
        db.add_question(**q)

    await update.message.reply_text(
        f"✅ {len(questions)} questions added successfully.\n"
        f"⚠️ {skipped} questions skipped (invalid format)."
    )

async def randomquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🔥 /randomquiz handler CALLED")

    chat = update.effective_chat
    chat_id = chat.id

    qids = db.get_unused_question_ids_for_chat(chat_id, limit=1)

    if not qids:
        admins = db.list_admins()
        text = "⚠️ Questions finished.\nPlease add more questions."

        for admin in admins:
            try:
                await context.bot.send_message(
                    chat_id=admin["user_id"],
                    text=text
                )
            except Exception as e:
                print("Notify admin error:", e)

        await update.message.reply_text(
            "⚠️ No questions available right now.\nAdmins have been notified."
        )
        return

    qid = qids[0]
    q = db.get_question_by_id(qid)

    if not q:
        await update.message.reply_text("❌ Failed to load question.")
        return

    options = [q["a"], q["b"], q["c"], q["d"]]
    correct_index = ["A", "B", "C", "D"].index(q["correct"])

    msg = await context.bot.send_poll(
        chat_id=chat_id,
        question=q["question"],
        options=options,
        type=Poll.QUIZ,
        correct_option_id=correct_index,
        explanation=q.get("explanation") or "",
        is_anonymous=False
    )

    # store poll info temporarily
    context.bot_data[msg.poll.id] = {
        "correct_index": correct_index,
        "chat_id": chat_id
    }

    # mark + count + delete question
    db.mark_question_sent(chat_id, qid)
    db.increment_attempted_questions()
    db.delete_question(qid)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll_answer = update.poll_answer
    user = poll_answer.user

    # ✅ ALWAYS save/update user name for global leaderboard
    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )

    selected_options = poll_answer.option_ids

    # Safety check
    if not selected_options:
        return

    chosen_index = selected_options[0]

    poll = context.bot_data.get(poll_answer.poll_id)
    if not poll:
        return

    correct_index = poll["correct_index"]
    chat_id = poll["chat_id"]

    is_correct = chosen_index == correct_index

    # Update global score
    db.update_global_score(user.id, is_correct)

    # ✅ COUNT THIS QUESTION AS ATTEMPTED (ADD THIS LINE)
    db.increment_attempted_questions()

    # Update group score (only if group)
    if chat_id < 0:
        db.update_group_score(
            chat_id=chat_id,
            user_id=user.id,
            username=user.username or user.first_name,
            is_correct=is_correct
        )

    # Compliment (GROUP ONLY)
    ctype = "correct" if is_correct else "wrong"
    compliment = db.get_random_compliment(ctype)

    if compliment and chat_id < 0:
        name = f"@{user.username}" if user.username else user.first_name
        text = compliment.replace("{user}", name)

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text
            )
        except Exception as e:
            logger.warning(f"Compliment not sent to group {chat_id}: {e}")


async def myscore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = db.get_global_score(user.id)

    if not stats:
        await update.message.reply_text("📊 No attempts yet.")
        return

    text = (
        f"📊 Your Score\n\n"
        f"Attempted: {stats['attempted']}\n"
        f"Correct: {stats['correct']}\n"
        f"Wrong: {stats['incorrect']}\n"
        f"Score: {stats['score']}"
    )

    await update.message.reply_text(apply_footer(text))

# ---------------- STATS COMMANDS ----------------

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    stats = db.get_global_user_stats(user.id)
    global_rank = db.get_global_rank(user.id)

    text = (
        f"📊 *Your Detailed Stats*\n\n"
        f"Attempts: {stats['attempted']}\n"
        f"✅ Correct: {stats['correct']}\n"
        f"❌ Wrong: {stats['incorrect']}\n"
        f"🏆 Score: {stats['score']}\n"
    )

    if global_rank:
        text += f"\n🌍 Global Rank: #{global_rank}"

    # Group rank only if used inside a group
    if chat.type in (Chat.GROUP, Chat.SUPERGROUP):
        group_rank = db.get_group_rank(chat.id, user.id)
        if group_rank:
            text += f"\n👥 Group Rank: #{group_rank}"

    await update.message.reply_text(apply_footer(text), parse_mode="Markdown")


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    board = db.get_global_leaderboard()

    if not board:
        await update.message.reply_text("📭 No leaderboard data yet.")
        return

    text = "🌍 *Global Leaderboard*\n\n"
    rank = 1

    for u in board:
        name = u["first_name"] or f"User {u['user_id']}"
        text += f"{rank}. {name} — 🏆 {u['score']}\n"
        rank += 1

    await update.message.reply_text(apply_footer(text), parse_mode="Markdown")

async def groupleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if chat.type == Chat.PRIVATE:
        await update.message.reply_text("❌ Group only command.")
        return

    board = db.get_group_leaderboard(chat.id)

    if not board:
        await update.message.reply_text("📭 No group stats yet.")
        return

    text = "👥 *Group Leaderboard*\n\n"
    rank = 1

    for u in board:
        name = u["username"] or str(u["user_id"])
        text += f"{rank}. {name} — 🏆 {u['score']}\n"
        rank += 1

    await update.message.reply_text(
        apply_footer(text),
        parse_mode="Markdown"
)

async def autoquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # PRIVATE CHAT ONLY
    if chat.type != Chat.PRIVATE:
        await update.message.reply_text("❌ Use this command in private chat only.")
        return

    # ADMIN ONLY
    if not db.is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    settings = db.get_global_autoquiz()

    if not context.args:
        status = "ON ✅" if settings["enabled"] else "OFF ❌"
        await update.message.reply_text(
            f"⚙️ *Global Auto Quiz*\n\n"
            f"Status: {status}\n"
            f"Interval: {settings['interval']} minutes",
            parse_mode="Markdown"
        )
        return

    arg = context.args[0].lower()

    if arg == "on":
        db.set_global_autoquiz(enabled=True)
        await update.message.reply_text("✅ Global Auto Quiz ENABLED")

    elif arg == "off":
        db.set_global_autoquiz(enabled=False)
        await update.message.reply_text("⛔ Global Auto Quiz DISABLED")

    elif arg == "interval" and len(context.args) == 2:
        try:
            minutes = int(context.args[1])
            if minutes < 5:
                raise ValueError
            db.set_global_autoquiz(interval=minutes)
            await update.message.reply_text(
                f"⏱ Interval set to {minutes} minutes"
            )
        except ValueError:
            await update.message.reply_text("❌ Interval must be a number ≥ 5")

    else:
        await update.message.reply_text(
            "Usage:\n"
            "/autoquiz\n"
            "/autoquiz on\n"
            "/autoquiz off\n"
            "/autoquiz interval 30"
        )

async def auto_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    settings = db.get_global_autoquiz()

    if not settings["enabled"]:
        return

    groups = db.get_all_groups()

    for chat_id in groups:
        try:
            qids = db.get_unused_question_ids_for_chat(chat_id, limit=1)
            if not qids:
                continue

            q = db.get_question_by_id(qids[0])
            if not q:
                continue

            options = [q["a"], q["b"], q["c"], q["d"]]
            correct_index = ["A", "B", "C", "D"].index(q["correct"])

            msg = await context.bot.send_poll(
                chat_id=chat_id,
                question=q["question"],
                options=options,
                type=Poll.QUIZ,
                correct_option_id=correct_index,
                explanation=q.get("explanation") or "",
                is_anonymous=False
            )

            context.bot_data[msg.poll.id] = {
                "correct_index": correct_index,
                "chat_id": chat_id
            }

            db.mark_question_sent(chat_id, q["id"])
            db.delete_question(q["id"])

        except Exception as e:
            logger.warning(f"Auto quiz failed in {chat_id}: {e}")

async def nightly_leaderboard_job(context: ContextTypes.DEFAULT_TYPE):
    groups = db.get_all_groups()

    if not groups:
        return

    # Build global leaderboard once
    global_text = build_global_leaderboard_text(limit=10)

    for chat_id in groups:
        try:
            # 1️⃣ Send GLOBAL leaderboard
            if global_text:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=global_text,
                    parse_mode="Markdown"
                )

            # 2️⃣ Send GROUP leaderboard
            group_text = build_group_leaderboard_text(chat_id, limit=10)
            if group_text:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=group_text,
                    parse_mode="Markdown"
                )

        except Exception as e:
            logger.warning(f"10PM leaderboard failed in {chat_id}: {e}")


async def questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = db.get_total_questions()
    left = db.get_questions_left()
    attempted = db.get_attempted_questions()

    text = (
        "📘 *Question Statistics*\n\n"
        f"📦 Total Questions: {total + attempted}\n"
        f"📂 Questions Left: {left}\n"
        f"✅ Questions Attempted: {attempted}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")

# ---------------- MAIN ----------------

def main():
    db.init_db()   # <-- ADD THIS

    if not BOT_TOKEN or BOT_TOKEN.startswith("PUT_"):
        raise RuntimeError("❌ BOT_TOKEN not set.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # BASIC
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    # OWNER / ADMIN
    app.add_handler(CommandHandler("addadmin", addadmin))
    app.add_handler(CommandHandler("removeadmin", removeadmin))
    app.add_handler(CommandHandler("adminlist", adminlist))

    # QUESTIONS
    app.add_handler(CommandHandler("addquestion", addquestion))
    app.add_handler(CommandHandler("randomquiz", randomquiz))
    app.add_handler(PollAnswerHandler(handle_poll_answer))
    app.add_handler(CommandHandler("myscore", myscore))
    app.add_handler(CommandHandler("mystats", mystats))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("groupleaderboard", groupleaderboard))
    app.add_handler(CommandHandler("addcompliment", addcompliment))
    app.add_handler(CommandHandler("listcompliments", listcompliments))
    app.add_handler(CommandHandler("autoquiz", autoquiz))
    app.add_handler(CommandHandler("questions", questions))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("footer", footer_cmd))

# ---- AUTO QUIZ JOB (STEP 4) ----
    settings = db.get_global_autoquiz()
    app.job_queue.run_repeating(
        auto_quiz_job,
        interval=settings["interval"] * 60,
        first=20
    )

    # ---- NIGHTLY LEADERBOARD JOB ----
    app.job_queue.run_daily(
        nightly_leaderboard_job,
        time=time(hour=13, minute=29),
    )

    print("✅ Nightly leaderboard job registered (10 PM)")

    logger.info("🤖 NEETIQBot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
