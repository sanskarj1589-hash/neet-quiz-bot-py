#!/usr/bin/env python3

import logging
from datetime import datetime, time

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

    ...
    board = db.get_group_leaderboard(chat_id, limit)
    if not board:
        return None

    text = "👥 Group Leaderboard\n\n"
    rank = 1

    for u in board:
        name = u["username"] or f"User {u['user_id']}"
        text += f"{rank}. {name} — 🏆 {u['score']}\n"
        rank += 1

    return apply_footer(text)

def build_group_leaderboard_message(chat_id: int, limit=10) -> str:
    board = db.get_group_leaderboard(chat_id, limit)

    if not board:
        return None

    text = "👥 *Group Leaderboard (Top 10)*\n\n"

    for i, u in enumerate(board, start=1):
        badge = rank_badge(i)
        name = u["username"] or f"User {u['user_id']}"

        text += (
            f"{badge} {name}\n"
            f"📘 Attempted: {u['attempted']} | "
            f"✅ Correct: {u['correct']} | "
            f"🏆 Score: {u['score']}\n\n"
        )

    # 🎉 ADD THIS AT THE END
    text += "🎉 *Congratulations everyone!*"

    return apply_footer(text)
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


def build_global_leaderboard_message(limit=10) -> str:
    board = db.get_global_leaderboard(limit=limit)

    if not board:
        return None

    text = "🌍 *Global Leaderboard (Top 10)*\n\n"

    for i, u in enumerate(board, start=1):
        badge = rank_badge(i)
        name = u["first_name"] or f"User {u['user_id']}"

        text += (
            f"{badge} {name}\n"
            f"📘 Attempted: {u['attempted']} | "
            f"✅ Correct: {u['correct']} | "
            f"🏆 Score: {u['score']}\n\n"
        )

    # 🎉 ADD THIS AT THE END
    text += "🎉 *Congratulations everyone!*"

    return apply_footer(text)

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
    chat = update.effective_chat

    print("🔥 BROADCAST HANDLER STARTED")

    # Admin only
    if not db.is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    # Private only
    if chat.type != Chat.PRIVATE:
        await update.message.reply_text("❌ Use this command in private chat.")
        return

    if not context.args:
        await update.message.reply_text("Usage:\n/broadcast Your message here")
        return

    message = " ".join(context.args)

    users = db.get_all_users()
    groups = db.get_all_groups()

    sent_users = failed_users = 0
    sent_groups = failed_groups = 0

    # ================= USERS =================
    for u in users:
        try:
            await context.bot.send_message(
                chat_id=int(u["user_id"]),
                text=message
            )
            sent_users += 1
        except Exception as e:
            failed_users += 1
            print("User failed:", u["user_id"], e)

    # ================= GROUPS =================
    for chat_id in groups:
        try:
            await context.bot.send_message(
                chat_id=int(chat_id),
                text=message
            )
            sent_groups += 1
        except Exception as e:
            failed_groups += 1
            print("Group failed:", chat_id, e)

    # ================= REPORT =================
    await update.message.reply_text(
        "📢 *Broadcast Report*\n\n"
        f"👤 Users:\n✅ Sent: {sent_users}\n❌ Failed: {failed_users}\n\n"
        f"👥 Groups:\n✅ Sent: {sent_groups}\n❌ Failed: {failed_groups}",
        parse_mode="Markdown"
    )

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
            "SELECT id, type, text FROM compliments ORDER BY id"
        ).fetchall()

    if not rows:
        await update.message.reply_text("📭 No compliments added yet.")
        return

    text = "💬 *Compliments List*\n\n"
    for r in rows:
        text += f"🆔 `{r['id']}` • ({r['type']}) {r['text']}\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def delcompliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not db.is_admin(user.id):
        await update.message.reply_text("❌ Admin only command.")
        return

    if not context.args:
        await update.message.reply_text("Usage:\n/delcompliment <id>")
        return

    try:
        cid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid compliment ID.")
        return

    with db.get_db() as conn:
        cur = conn.execute(
            "DELETE FROM compliments WHERE id = ?",
            (cid,)
        )

    if cur.rowcount == 0:
        await update.message.reply_text("⚠️ No compliment found with this ID.")
    else:
        await update.message.reply_text("🗑️ Compliment deleted successfully.")

async def botstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = db.get_total_users()
    total_groups = db.get_total_groups()
    total_questions = db.get_total_questions()
    attempted_users = db.get_users_who_attempted()

    text = (
        "🤖 *Bot Statistics*\n\n"
        f"👤 Total Users: {total_users}\n"
        f"👥 Total Groups: {total_groups}\n"
        f"📘 Total Questions: {total_questions}\n"
        f"🧠 Users Attempted Quiz: {attempted_users}"
    )

    await update.message.reply_text(
        apply_footer(text),
        parse_mode="Markdown"
    )

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

    # Save / update user
    db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )

    if not poll_answer.option_ids:
        return

    chosen_index = poll_answer.option_ids[0]

    poll = context.bot_data.get(poll_answer.poll_id)
    if not poll:
        return

    correct_index = poll["correct_index"]
    chat_id = poll["chat_id"]

    is_correct = chosen_index == correct_index

    # ---------------- GLOBAL SCORE ----------------
    db.update_global_score(user.id, is_correct)
    db.increment_attempted_questions()

    # ---------------- STREAK LOGIC ----------------
    stats = db.get_global_user_stats(user.id)

    current_streak = stats.get("current_streak", 0)
    best_streak = stats.get("best_streak", 0)
    daily_streak = stats.get("daily_streak", 0)
    max_streak = stats.get("max_streak", 0)

    today = datetime.utcnow().date().isoformat()
    last_date = stats.get("last_attempt_date")

    # Daily streak handling
    if last_date == today:
        pass
    else:
        daily_streak = daily_streak + 1 if last_date else 1

    if is_correct:
        current_streak += 1
        best_streak = max(best_streak, current_streak)
        max_streak = max(max_streak, best_streak)
    else:
        current_streak = 0

    db.update_streaks(
        user_id=user.id,
        current_streak=current_streak,
        best_streak=best_streak,
        daily_streak=daily_streak,
        max_streak=max_streak,
        last_attempt_date=today
    )

    # ---------------- STREAK CELEBRATION ----------------
    if is_correct and current_streak in (3, 5, 10):
        name = f"@{user.username}" if user.username else user.first_name
        msg = (
            f"🔥 *{current_streak} Correct in a Row!*\n"
            f"{name} congo 🎉👏"
        )
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode="Markdown"
            )
        except:
            pass

    # ---------------- GROUP SCORE ----------------
    if chat_id < 0:
        db.update_group_score(
            chat_id=chat_id,
            user_id=user.id,
            username=user.username or user.first_name,
            is_correct=is_correct
        )

    # ---------------- COMPLIMENT ----------------
    ctype = "correct" if is_correct else "wrong"
    compliment = db.get_random_compliment(ctype)

    if compliment and chat_id < 0:
        name = f"@{user.username}" if user.username else user.first_name
        text = compliment.replace("{user}", name)
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            logger.warning(f"Compliment failed in {chat_id}: {e}")

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

    attempted = stats["attempted"]
    correct = stats["correct"]
    incorrect = stats["incorrect"]
    score = stats["score"]

    best_streak = stats["best_streak"]
    daily_streak = stats["daily_streak"]
    max_streak = stats["max_streak"]

    accuracy = (correct / attempted * 100) if attempted > 0 else 0

    text = (
        "📊 *Your Stats*\n\n"
        f"📘 Attempts: {attempted}\n"
        f"✅ Correct: {correct}\n"
        f"❌ Wrong: {incorrect}\n"
        f"🎯 Accuracy: {accuracy:.2f}%\n"
        f"🔥 Best Streak: {best_streak}\n\n"
        f"🌞 Daily Streak: {daily_streak}\n"
        f"🏆 Max Streak: {max_streak}\n\n"
        f"🏆 Score: {score}\n"
    )

    if global_rank:
        text += f"\n🌍 Global Rank: #{global_rank}"

    if chat.type in (Chat.GROUP, Chat.SUPERGROUP):
        group_rank = db.get_group_rank(chat.id, user.id)
        if group_rank:
            text += f"\n👥 Group Rank: #{group_rank}"

    await update.message.reply_text(
        apply_footer(text),
        parse_mode="Markdown"
    )


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    board = db.get_global_leaderboard(limit=25)

    if not board:
        await update.message.reply_text("📭 No leaderboard data yet.")
        return

    text = "🌍 *Global Leaderboard (Top 25)*\n\n"

    for i, u in enumerate(board, start=1):
        badge = rank_badge(i)
        name = u["first_name"] or f"User {u['user_id']}"

        text += (
            f"{badge} {name}\n"
            f"📘 Attempted: {u['attempted']} | "
            f"✅ Correct: {u['correct']} | "
            f"🏆 Score: {u['score']}\n\n"
        )

    await update.message.reply_text(
        apply_footer(text),
        parse_mode="Markdown"
    )

def rank_badge(rank: int) -> str:
    if rank == 1:
        return "🥇"
    elif rank == 2:
        return "🥈"
    elif rank == 3:
        return "🥉"
    else:
        return f"{rank}."

async def groupleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if chat.type == Chat.PRIVATE:
        await update.message.reply_text("❌ Group only command.")
        return

    board = db.get_group_leaderboard(chat.id, limit=10)

    if not board:
        await update.message.reply_text("📭 No group stats yet.")
        return

    text = "👥 *Group Leaderboard (Top 10)*\n\n"

    for i, u in enumerate(board, start=1):
        badge = rank_badge(i)
        name = u["username"] or f"User {u['user_id']}"

        text += (
            f"{badge} {name}\n"
            f"📘 Attempted: {u['attempted']} | "
            f"✅ Correct: {u['correct']} | "
            f"🏆 Score: {u['score']}\n\n"
        )

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
    print("📦 GROUPS FOUND:", groups)

    if not groups:
        return

    # Build global leaderboard once
    global_text = build_global_leaderboard_message(limit=10)

    for chat_id in groups:
        try:
            # 🌍 Global Leaderboard
            if global_text:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=global_text,
                    parse_mode="Markdown"
                )

            # 👥 Group Leaderboard
            group_text = build_group_leaderboard_message(chat_id, limit=10)
            if group_text:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=group_text,
                    parse_mode="Markdown"
                )

        except Exception as e:
            logger.warning(f"🌙 Nightly leaderboard failed in {chat_id}: {e}")


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

async def testleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧪 Running leaderboard job manually...")
    await nightly_leaderboard_job(context)

# ---------------- MAIN ----------------

def main():
    db.init_db()   # initialize database

    if not BOT_TOKEN or BOT_TOKEN.startswith("PUT_"):
        raise RuntimeError("❌ BOT_TOKEN not set.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ---------------- BASIC ----------------
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    # ---------------- ADMIN ----------------
    app.add_handler(CommandHandler("addadmin", addadmin))
    app.add_handler(CommandHandler("removeadmin", removeadmin))
    app.add_handler(CommandHandler("adminlist", adminlist))

    # ---------------- QUIZ ----------------
    app.add_handler(CommandHandler("addquestion", addquestion))
    app.add_handler(CommandHandler("randomquiz", randomquiz))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    # ---------------- STATS ----------------
    app.add_handler(CommandHandler("myscore", myscore))
    app.add_handler(CommandHandler("mystats", mystats))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("groupleaderboard", groupleaderboard))
    app.add_handler(CommandHandler("questions", questions))
    app.add_handler(CommandHandler("testleaderboard", testleaderboard))
    app.add_handler(CommandHandler("botstats", botstats))

    # ---------------- EXTRAS ----------------
    app.add_handler(CommandHandler("addcompliment", addcompliment))
    app.add_handler(CommandHandler("listcompliments", listcompliments))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("footer", footer_cmd))
    app.add_handler(CommandHandler("autoquiz", autoquiz))
    app.add_handler(CommandHandler("delcompliment", delcompliment))

    # ---------------- AUTO QUIZ JOB ----------------
    settings = db.get_global_autoquiz()
    app.job_queue.run_repeating(
        auto_quiz_job,
        interval=settings["interval"] * 60,
        first=20
    )

    # ---------------- NIGHTLY LEADERBOARD JOB ----------------
    app.job_queue.run_daily(
        nightly_leaderboard_job,
        time=time(hour=21, minute=0)  # test time
    )

    logger.info("🌙 Nightly leaderboard job registered")
    logger.info("🤖 NEETIQBot is running...")

    app.run_polling()

if __name__ == "__main__":
