import logging
import asyncio
import pytz 
import os
from datetime import datetime, time
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    PollAnswerHandler,
    MessageHandler,
    filters,
    Defaults
)
import database as db

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6435499094

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

defaults = Defaults(parse_mode=None)

# ---------------- HELPERS ----------------

def apply_footer(text: str) -> str:
    """Applies the professional divider and custom footer text."""
    with db.get_db() as conn:
        f_res = conn.execute("SELECT value FROM settings WHERE key='footer_text'")
        e_res = conn.execute("SELECT value FROM settings WHERE key='footer_enabled'")
    
    footer_text = f_res.rows[0][0] if f_res.rows else "NEETIQBot"
    enabled = e_res.rows[0][0] if e_res.rows else "1"
    
    if enabled == '1':
        return f"{text}\n\n━━━━━━━━━━━━━━━\n{footer_text}"
    return text

async def is_admin(user_id: int) -> bool:
    """Check if a user has admin privileges or is the owner."""
    if user_id == OWNER_ID:
        return True
    with db.get_db() as conn:
        res = conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
        return len(res.rows) > 0

# ---------------- REGISTRATION ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at) VALUES (?,?,?,?)",
            (user.id, user.username, user.first_name, str(datetime.now()))
        )
        if chat.type != 'private':
            conn.execute(
                "INSERT OR IGNORE INTO chats (chat_id, type, title, added_at) VALUES (?,?,?,?)",
                (chat.id, chat.type, chat.title, str(datetime.now()))
            )

    if chat.type == 'private':
        welcome = (
            f"👋 *Welcome to NEETIQBot, {user.first_name}!*\n\n"
            "I am your dedicated NEET preparation assistant.\n\n"
            "📌 *Use* /help *to see all available commands.*"
        )
        btn = [[InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]]
        await update.message.reply_text(apply_footer(welcome), reply_markup=InlineKeyboardMarkup(btn))
    else:
        group_msg = f"🎉 *Group successfully registered with NEETIQBot!*"
        await update.message.reply_text(apply_footer(group_msg))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 *NEETIQBot Command List*\n\n"
        "/start - Register\n"
        "/randomquiz - Get a random MCQ\n"
        "/myscore - View score\n"
        "/mystats - Detailed stats\n"
        "/leaderboard - Global rankings"
    )
    await update.message.reply_text(apply_footer(help_text))

# ---------------- QUIZ SYSTEM ----------------

async def send_random_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    with db.get_db() as conn:
        res = conn.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT 1")
    
    if not res.rows:
        return await update.message.reply_text("📭 *Database Empty!*")

    q = res.rows[0]
    options = [q['a'], q['b'], q['c'], q['d']]
    correct_map = {'1': 0, '2': 1, '3': 2, '4': 3, 'A': 0, 'B': 1, 'C': 2, 'D': 3}
    c_idx = correct_map.get(str(q['correct']).upper(), 0)

    try:
        msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"🧠 *NEET MCQ:*\n\n{q['question']}",
            options=options,
            type=Poll.QUIZ,
            correct_option_id=c_idx,
            explanation=f"📖 *Explanation:*\n{q['explanation']}",
            is_anonymous=False
        )
        
        with db.get_db() as conn:
            conn.execute("INSERT INTO active_polls VALUES (?,?,?)", (msg.poll.id, chat_id, c_idx))
            conn.execute("DELETE FROM questions WHERE id = ?", (q['id'],))
            
    except Exception as e:
        logger.error(f"Error in Quiz Flow: {e}")

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user

    with db.get_db() as conn:
        res = conn.execute("SELECT * FROM active_polls WHERE poll_id = ?", (poll_id,))

    if not res.rows:
        return

    poll_data = res.rows[0]
    chat_id = poll_data['chat_id']
    correct_option = poll_data['correct_option_id']
    is_correct = (answer.option_ids[0] == correct_option)

    db.update_user_stats(user.id, chat_id, is_correct, username=user.username, first_name=user.first_name)

    with db.get_db() as conn:
        s_res = conn.execute("SELECT compliments_enabled FROM group_settings WHERE chat_id = ?", (chat_id,))
        if s_res.rows and s_res.rows[0][0] == 0:
            return

    c_type = "correct" if is_correct else "wrong"
    
    with db.get_db() as conn:
        comp_res = conn.execute("SELECT text FROM group_compliments WHERE chat_id = ? AND type = ? ORDER BY RANDOM() LIMIT 1", (chat_id, c_type))
        if not comp_res.rows:
            comp_res = conn.execute("SELECT text FROM compliments WHERE type = ? ORDER BY RANDOM() LIMIT 1", (c_type,))

    if comp_res.rows:
        compliment_text = comp_res.rows[0][0]
        mention_name = f"@{user.username}" if user.username else f"*{user.first_name}*"
        final_text = compliment_text.replace("{user}", mention_name)
        if chat_id < 0:
            try:
                await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode="Markdown")
            except Exception: pass

# ---------------- STATS & LEADERBOARD ----------------

async def myscore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    with db.get_db() as conn:
        res = conn.execute("SELECT * FROM stats WHERE user_id = ?", (user.id,))
    
    if not res.rows:
        return await update.message.reply_text("❌ *No data found.*")

    s = res.rows[0]
    text = (f"📊 *Your Score Summary*\n\nAttempted: `{s['attempted']}`\nCorrect: `{s['correct']}`\nScore: `{s['score']}`")
    await update.message.reply_text(apply_footer(text))

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    with db.get_db() as conn:
        res = conn.execute("SELECT * FROM stats WHERE user_id = ?", (user.id,))
        if not res.rows:
            return await update.message.reply_text("❌ *No statistics available yet!*")
        s = res.rows[0]
        rank_res = conn.execute("SELECT COUNT(*) + 1 FROM stats WHERE score > ?", (s['score'],))
        rank_val = rank_res.rows[0][0]

    accuracy = (s['correct'] / s['attempted'] * 100) if s['attempted'] > 0 else 0
    text = (f"📊 *Detailed Performance*\n\nAccuracy: `{accuracy:.2f}%`\nStreak: `{s['current_streak']}`\nGlobal Rank: `#{rank_val}`")
    await update.message.reply_text(apply_footer(text))

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_leaderboard_data(limit=25)
    if not rows:
        return await update.message.reply_text("📭 Leaderboard is empty.")

    text = "🌍 *Global Leaderboard*\n\n"
    for i, r in enumerate(rows, 1):
        text += f"#{i} {r[0]} - ⭐ {r[3]} pts!\n"
    await update.message.reply_text(apply_footer(text))

async def groupleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        return await update.message.reply_text("❌ Groups only.")
    rows = db.get_leaderboard_data(chat_id=update.effective_chat.id, limit=10)
    text = f"👥 *{update.effective_chat.title} Leaderboard*\n\n"
    for i, r in enumerate(rows, 1):
        text += f"#{i} {r[0]} - ⭐ {r[3]} pts!\n"
    await update.message.reply_text(apply_footer(text))

# ---------------- ADMIN & JOBS ----------------

async def addquestion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id): return
    content = ""
    if update.message.document and update.message.document.file_name.endswith('.txt'):
        file = await context.bot.get_file(update.message.document.file_id)
        content = (await file.download_as_bytearray()).decode('utf-8')
    elif update.message.text:
        content = update.message.text.replace("/addquestion", "").strip()

    raw_entries = [e.strip() for e in content.split('\n\n') if e.strip()]
    added = 0
    with db.get_db() as conn:
        for entry in raw_entries:
            lines = [l.strip() for l in entry.split('\n') if l.strip()]
            if len(lines) >= 7:
                conn.execute("INSERT INTO questions (question, a, b, c, d, correct, explanation) VALUES (?,?,?,?,?,?,?)",
                             ("\n".join(lines[:-6]), lines[-6], lines[-5], lines[-4], lines[-3], lines[-2], lines[-1]))
                added += 1
    await update.message.reply_text(f"✅ Added: `{added}` questions")

async def auto_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    with db.get_db() as conn:
        s_res = conn.execute("SELECT value FROM settings WHERE key='autoquiz_enabled'")
        if not s_res.rows or s_res.rows[0][0] == '0': return
        q_res = conn.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT 1")
        if not q_res.rows: return
        q = q_res.rows[0]
        chat_res = conn.execute("SELECT chat_id FROM chats WHERE type != 'private'")
        chats = chat_res.rows

    options = [q['a'], q['b'], q['c'], q['d']]
    correct_map = {'1': 0, '2': 1, '3': 2, '4': 3, 'A': 0, 'B': 1, 'C': 2, 'D': 3}
    c_idx = correct_map.get(str(q['correct']).upper(), 0)

    for c in chats:
        try:
            msg = await context.bot.send_poll(chat_id=c[0], question=f"🧠 *Global Quiz:*\n\n{q['question']}", options=options, type=Poll.QUIZ, correct_option_id=c_idx, is_anonymous=False)
            with db.get_db() as conn:
                conn.execute("INSERT INTO active_polls VALUES (?,?,?)", (msg.poll.id, c[0], c_idx))
            await asyncio.sleep(0.2)
        except Exception: continue
    with db.get_db() as conn:
        conn.execute("DELETE FROM questions WHERE id = ?", (q['id'],))

# ... (Include other simple handlers like broadcast, footer_cmd etc using the .rows logic) ...

if __name__ == '__main__':
    db.init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).defaults(defaults).build()

    handlers = [
        CommandHandler("start", start), CommandHandler("help", help_command),
        CommandHandler("randomquiz", send_random_quiz), CommandHandler("myscore", myscore),
        CommandHandler("mystats", mystats), CommandHandler("leaderboard", leaderboard),
        CommandHandler("groupleaderboard", groupleaderboard), CommandHandler("addquestion", addquestion),
        MessageHandler(filters.Document.ALL, addquestion), PollAnswerHandler(handle_poll_answer)
    ]
    for h in handlers: app.add_handler(h)

    try:
        with db.get_db() as conn:
            i_res = conn.execute("SELECT value FROM settings WHERE key='autoquiz_interval'")
            interval_min = int(i_res.rows[0][0]) if i_res.rows else 30
    except Exception: interval_min = 30 

    app.job_queue.run_repeating(auto_quiz_job, interval=interval_min * 60, first=20)
    print("🚀 NEETIQBot Master is Online!")
    app.run_polling(drop_pending_updates=True)

