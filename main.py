import logging
import asyncio
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
# Replace with your actual Bot Token
BOT_TOKEN = "8203396114:AAE_Ii9RuLvhCA64PRPwq1BZVc7bEPZmq0g"
OWNER_ID = 6435499094

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

defaults = Defaults(parse_mode="Markdown")

# ---------------- HELPERS ----------------

def apply_footer(text: str) -> str:
    """Applies the professional divider and custom footer text (PostgreSQL version)."""
    with db.get_db() as cur:
        cur.execute("SELECT value FROM settings WHERE key='footer_text'")
        f_row = cur.fetchone()
        cur.execute("SELECT value FROM settings WHERE key='footer_enabled'")
        f_en = cur.fetchone()
    
    footer_text = f_row['value'] if f_row else "NEETIQBot"
    enabled = f_en['value'] if f_en else "1"
    
    if enabled == '1':
        return f"{text}\n\n━━━━━━━━━━━━━━━\n{footer_text}"
    return text

async def is_admin(user_id: int) -> bool:
    """Check if a user has admin privileges (PostgreSQL %s placeholder)."""
    if user_id == OWNER_ID:
        return True
    with db.get_db() as cur:
        cur.execute("SELECT 1 FROM admins WHERE user_id=%s", (user_id,))
        res = cur.fetchone()
        return res is not None

# ---------------- REGISTRATION ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    with db.get_db() as cur:
        cur.execute(
            """INSERT INTO users (user_id, username, first_name, joined_at) 
               VALUES (%s,%s,%s,%s) ON CONFLICT (user_id) DO NOTHING""",
            (user.id, user.username, user.first_name, str(datetime.now()))
        )
        if chat.type != 'private':
            cur.execute(
                """INSERT INTO chats (chat_id, type, title, added_at) 
                   VALUES (%s,%s,%s,%s) ON CONFLICT (chat_id) DO NOTHING""",
                (chat.id, chat.type, chat.title, str(datetime.now()))
            )

    if chat.type == 'private':
        welcome = (
            f"👋 *Welcome to NEETIQBot, {user.first_name}!*\n\n"
            "I am your dedicated NEET preparation assistant. "
            "I provide high-quality MCQs, track your streaks, and manage competitive leaderboards.\n\n"
            "📌 *Use* /help *to see all available commands.*"
        )
        btn = [[InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]]
        await update.message.reply_text(apply_footer(welcome), reply_markup=InlineKeyboardMarkup(btn))
    else:
        group_msg = f"🎉 *Group successfully registered with NEETIQBot!*\n\nPreparing {chat.title} for upcoming quizzes."
        await update.message.reply_text(apply_footer(group_msg))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 *NEETIQBot Command List*\n\n"
        "👋 *Basic Commands*\n"
        "/start - Register and start the bot\n"
        "/help - Display this help manual\n\n"
        "📘 *Quiz System*\n"
        "/randomquiz - Receive a random NEET MCQ\n"
        "/myscore - View your point summary\n"
        "/mystats - Detailed performance analysis\n\n"
        "🏆 *Leaderboards*\n"
        "/leaderboard - Global rankings (Top 25)\n"
        "/groupleaderboard - Group specific rankings"
    )
    await update.message.reply_text(apply_footer(help_text))

  # ---------------- QUIZ SYSTEM ----------------

async def send_random_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a random NEET MCQ and permanently deletes it from the DB to prevent repetition."""
    chat_id = update.effective_chat.id
    
    with db.get_db() as cur:
        # PostgreSQL uses RANDOM()
        cur.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT 1")
        q = cur.fetchone()

    if not q:
        return await update.message.reply_text(
            "📭 *Database Empty!* All questions have been used and deleted. "
            "Please upload new questions using /addquestion."
        )

    options = [q['a'], q['b'], q['c'], q['d']]
    
    # Map correct answer (supports 1-4 or A-D)
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
        
        with db.get_db() as cur:
            # PostgreSQL syntax for active_polls
            cur.execute("INSERT INTO active_polls (poll_id, chat_id, correct_option_id) VALUES (%s,%s,%s)", 
                        (msg.poll.id, chat_id, c_idx))
            # Delete by ID
            cur.execute("DELETE FROM questions WHERE id = %s", (q['id'],))
            
    except Exception as e:
        logger.error(f"Error in Quiz Flow: {e}")
        await update.message.reply_text("❌ Failed to process the quiz.")

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes the user's answer and updates streaks/scores."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = answer.user.id

    with db.get_db() as cur:
        cur.execute("SELECT * FROM active_polls WHERE poll_id = %s", (poll_id,))
        poll_data = cur.fetchone()

    if not poll_data:
        return

    chat_id = poll_data['chat_id']
    correct_option = poll_data['correct_option_id']
    is_correct = (answer.option_ids[0] == correct_option)

    db.update_user_stats(user_id, chat_id, is_correct)

    with db.get_db() as cur:
        cur.execute("SELECT compliments_enabled FROM group_settings WHERE chat_id = %s", (chat_id,))
        setting = cur.fetchone()
        if setting and setting['compliments_enabled'] == 0:
            return 

    c_type = "correct" if is_correct else "wrong"
    
    with db.get_db() as cur:
        cur.execute(
            "SELECT text FROM group_compliments WHERE chat_id = %s AND type = %s ORDER BY RANDOM() LIMIT 1",
            (chat_id, c_type)
        )
        comp = cur.fetchone()
        
        if not comp:
            cur.execute("SELECT text FROM compliments WHERE type = %s ORDER BY RANDOM() LIMIT 1", (c_type,))
            comp = cur.fetchone()

    if comp:
        final_text = comp['text'].replace("{user}", f"*{answer.user.first_name}*")
        if chat_id < 0: 
            try:
                await context.bot.send_message(chat_id=chat_id, text=final_text)
            except Exception: pass

# ---------------- PERFORMANCE STATS ----------------

async def myscore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    with db.get_db() as cur:
        cur.execute("SELECT * FROM stats WHERE user_id = %s", (user.id,))
        s = cur.fetchone()
    
    if not s:
        return await update.message.reply_text("❌ *No data found.*")

    text = (
        "📊 *Your Score Summary*\n\n"
        f"Total Attempted: `{s['attempted']}`\n"
        f"Correct Answers: `{s['correct']}`\n"
        f"Current Score: `{s['score']}`"
    )
    await update.message.reply_text(apply_footer(text))


# ---------------- LEADERBOARD LOGIC ----------------

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_leaderboard_data(limit=25)
    if not rows:
        return await update.message.reply_text("📭 Leaderboard is empty.")

    text = "🌍 *Global Leaderboard (Top 25)*\n\n"
    for i, r in enumerate(rows, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        text += f"{medal} *{r['first_name']}*\n📘 Att: `{r['attempted']}` | ✅ Cor: `{r['correct']}` | 🏆 Score: `{r['score']}`\n\n"
    
    await update.message.reply_text(apply_footer(text))

async def groupleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        return await update.message.reply_text("❌ Only available in Groups.")

    chat_id = update.effective_chat.id
    rows = db.get_leaderboard_data(chat_id=chat_id, limit=10)

    text = f"👥 *{update.effective_chat.title} Leaderboard*\n\n"
    if not rows:
        text += "No participants yet."
    else:
        for i, r in enumerate(rows, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            text += f"{medal} *{r['first_name']}*\n📘 Att: `{r['attempted']}` | ✅ Cor: `{r['correct']}` | 🏆 Score: `{r['score']}`\n\n"
    
    await update.message.reply_text(apply_footer(text))
# ---------------- ADMIN & MANAGEMENT ----------------


import re

async def addquestion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id): return
    
    text = ""
    if update.message.document:
        file = await update.message.document.get_file()
        content = await file.download_as_bytearray()
        text = content.decode('utf-8')
    else:
        # Get text after /addquestion
        parts = update.message.text.split(None, 1)
        text = parts[1] if len(parts) > 1 else ""

    if not text:
        return await update.message.reply_text("📂 Please provide questions in the numbered format.")

    # Regex to split by "1. ", "2. ", etc.
    q_blocks = re.split(r'\n\d+\.\s+', "\n" + text.strip())[1:]
    
    added_count = 0
    with db.get_db() as cur:
        for block in q_blocks:
            lines = [l.strip() for l in block.split('\n') if l.strip()]
            if len(lines) >= 7:
                # Question | A | B | C | D | Correct | Explanation
                # lines[1][3:] removes the "A. " prefix
                cur.execute(
                    "INSERT INTO questions (question, a, b, c, d, correct, explanation) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (lines[0], lines[1][3:], lines[2][3:], lines[3][3:], lines[4][3:], lines[5], lines[6])
                )
                added_count += 1
    
    await update.message.reply_text(f"✅ Successfully added `{added_count}` questions.")
    


# ---------------- GROUP CUSTOMIZATION ----------------

async def set_compliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private': return
    # Only group admins can use this
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ['administrator', 'creator']: return

    if len(context.args) < 2:
        return await update.message.reply_text("❌ Usage: /setcomp <correct/wrong> <text>\nExample: `/setcomp correct Great job {user}!`")
    
    c_type = context.args[0].lower()
    c_text = " ".join(context.args[1:])
    chat_id = update.effective_chat.id

    with db.get_db() as cur:
        cur.execute("DELETE FROM group_compliments WHERE chat_id=%s AND type=%s", (chat_id, c_type))
        cur.execute("INSERT INTO group_compliments (chat_id, type, text) VALUES (%s,%s,%s)", (chat_id, c_type, c_text))
    await update.message.reply_text(f"✅ Custom {c_type} message saved for this group!")

# ---------------- SCHEDULER & AUTO-QUIZ ----------------

async def auto_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    with db.get_db() as cur:
        cur.execute("SELECT value FROM settings WHERE key='autoquiz_enabled'")
        enabled = cur.fetchone()
        if not enabled or enabled['value'] == '0': return

        cur.execute("SELECT chat_id FROM chats")
        groups = cur.fetchall()
        cur.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT 1")
        q = cur.fetchone()

    if not q or not groups: return

    options = [q['a'], q['b'], q['c'], q['d']]
    correct_map = {'1': 0, '2': 1, '3': 2, '4': 3, 'A': 0, 'B': 1, 'C': 2, 'D': 3}
    c_idx = correct_map.get(str(q['correct']).upper(), 0)

    for g in groups:
        try:
            msg = await context.bot.send_poll(
                chat_id=g['chat_id'],
                question=f"🕒 *Scheduled MCQ:*\n\n{q['question']}",
                options=options,
                type=Poll.QUIZ,
                correct_option_id=c_idx,
                explanation=f"📖 *Explanation:*\n{q['explanation']}",
                is_anonymous=False
            )
            with db.get_db() as cur:
                cur.execute("INSERT INTO active_polls (poll_id, chat_id, correct_option_id) VALUES (%s,%s,%s)", 
                            (msg.poll.id, g['chat_id'], c_idx))
        except: continue
    
    with db.get_db() as cur:
        cur.execute("DELETE FROM questions WHERE id=%s", (q['id'],))

# ---------------- CONFIGURATION COMMANDS ----------------

async def footer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage the bot footer: /footer <text> or /footer toggle"""
    if not await is_admin(update.effective_user.id): return
    
    if not context.args:
        return await update.message.reply_text("📂 *Footer Settings*\n`/footer <text>` - Set text\n`/footer toggle` - Enable/Disable")
    
    cmd = context.args[0].lower()
    with db.get_db() as cur:
        if cmd == 'toggle':
            cur.execute("SELECT value FROM settings WHERE key='footer_enabled'")
            current = cur.fetchone()['value']
            new_val = '0' if current == '1' else '1'
            cur.execute("UPDATE settings SET value=%s WHERE key='footer_enabled'", (new_val,))
            status = "Enabled" if new_val == '1' else "Disabled"
            await update.message.reply_text(f"✅ Footer is now *{status}*.")
        else:
            new_text = " ".join(context.args)
            cur.execute("UPDATE settings SET value=%s WHERE key='footer_text'", (new_text,))
            await update.message.reply_text(f"✅ Footer text updated to: `{new_text}`")

async def autoquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage Auto-Quiz: /autoquiz <on/off> or /autoquiz interval <min>"""
    if not await is_admin(update.effective_user.id): return
    
    if not context.args:
        return await update.message.reply_text("🕒 *Auto-Quiz Settings*\n`/autoquiz on/off` - Toggle\n`/autoquiz interval <min>` - Set time")

    sub = context.args[0].lower()
    with db.get_db() as cur:
        if sub in ['on', 'off']:
            val = '1' if sub == 'on' else '0'
            cur.execute("UPDATE settings SET value=%s WHERE key='autoquiz_enabled'", (val,))
            await update.message.reply_text(f"✅ Auto-quiz turned *{sub.upper()}*.")
        elif sub == 'interval' and len(context.args) > 1:
            mins = context.args[1]
            cur.execute("UPDATE settings SET value=%s WHERE key='autoquiz_interval'", (mins,))
            await update.message.reply_text(f"✅ Interval set to `{mins}` minutes. (Restart bot to apply immediately)")

# ---------------- COMPLIMENTS MANAGEMENT ----------------

async def addcompliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id): return
    if len(context.args) < 2:
        return await update.message.reply_text("❌ Usage: /addcompliment <correct/wrong> <text>")
    
    c_type = context.args[0].lower()
    c_text = " ".join(context.args[1:])
    with db.get_db() as cur:
        cur.execute("INSERT INTO compliments (type, text) VALUES (%s, %s)", (c_type, c_text))
    await update.message.reply_text(f"✅ Global {c_type} compliment added.")

async def listcompliments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id): return
    with db.get_db() as cur:
        cur.execute("SELECT * FROM compliments")
        rows = cur.fetchall()
    
    if not rows: return await update.message.reply_text("📭 No compliments found.")
    
    text = "📜 *Global Compliments:*\n"
    for r in rows:
        text += f"ID: `{r['id']}` | {r['type'].upper()}: {r['text']}\n"
    await update.message.reply_text(text)

async def delcompliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id): return
    try:
        c_id = int(context.args[0])
        with db.get_db() as cur:
            cur.execute("DELETE FROM compliments WHERE id=%s", (c_id,))
        await update.message.reply_text(f"✅ Compliment `{c_id}` deleted.")
    except: await update.message.reply_text("❌ Usage: /delcompliment <id>")

# ---------------- EXTRA ADMIN HELPERS ----------------

async def adminlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id): return
    with db.get_db() as cur:
        cur.execute("SELECT user_id FROM admins")
        rows = cur.fetchall()
    
    text = f"👑 *Bot Admins:*\nOwner: `{OWNER_ID}`\n"
    for r in rows:
        text += f"• `{r['user_id']}`\n"
    await update.message.reply_text(text)

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        admin_id = int(context.args[0])
        with db.get_db() as cur:
            cur.execute("DELETE FROM admins WHERE user_id=%s", (admin_id,))
        await update.message.reply_text(f"✅ User `{admin_id}` removed from Admins.")
    except: await update.message.reply_text("❌ Usage: /removeadmin <user_id>")

async def questions_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id): return
    with db.get_db() as cur:
        cur.execute("SELECT COUNT(*) as count FROM questions")
        res = cur.fetchone()
    await update.message.reply_text(f"📚 *Question Bank Status*\nTotal MCQs remaining: `{res['count']}`")

# 1. ADMIN MANAGEMENT FIXES
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        admin_id = int(context.args[0])
        with db.get_db() as cur:
            cur.execute("INSERT INTO admins (user_id, added_at) VALUES (%s, %s) ON CONFLICT DO NOTHING", 
                        (admin_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        await update.message.reply_text(f"✅ User `{admin_id}` added as Admin.")
    except: await update.message.reply_text("❌ Usage: /addadmin <user_id>")

# 2. BROADCAST (Preserves spacing and shows separate counts)
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id): return
    # msg_text_raw preserves the exact spacing/formatting from your message
    msg_text = update.message.text_markdown.split(None, 1)[1] if len(context.args) > 0 else None
    if not msg_text: return await update.message.reply_text("❌ Usage: /broadcast <message>")
    
    with db.get_db() as cur:
        cur.execute("SELECT user_id FROM users")
        users = cur.fetchall()
        cur.execute("SELECT chat_id FROM chats")
        chats = cur.fetchall()

    u_success, g_success = 0, 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u['user_id'], text=msg_text)
            u_success += 1
            await asyncio.sleep(0.05) # Prevent spam limits
        except: continue
    for c in chats:
        try:
            await context.bot.send_message(chat_id=c['chat_id'], text=msg_text)
            g_success += 1
            await asyncio.sleep(0.05)
        except: continue
    
    await update.message.reply_text(f"✅ *Broadcast Complete:*\nUsers: {u_success}\nGroups: {g_success}")

# 3. BOT STATS (Your exact requested layout)
async def bot_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id): return
    data = db.get_bot_stats()
    text = (
        "🤖 *NEETIQ Master Bot Statistics*\n\n"
        f"👤 Total Users: {data['users']}\n"
        f"👥 Total Groups: {data['groups']}\n"
        f"👮 Total Admins: {data['admins']}\n\n"
        "📊 *Database Growth*\n\n"
        f"❓ Total Questions left: {data['q_left']}\n"
        f"📝 Total questions conducted: {data['q_conducted']}\n"
        f"📝 Total Global Attempts [today]: {data['att_today']}\n"
        f"📝 Total Global Attempts: {data['att_total']}"
    )
    await update.message.reply_text(apply_footer(text))

# 4. MY STATS (Detailed performance with Ranks)
async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    with db.get_db() as cur:
        cur.execute("SELECT * FROM stats WHERE user_id = %s", (user.id,))
        s = cur.fetchone()
        
        # Calculate Global Rank
        rank_val = "N/A"
        if s:
            cur.execute("SELECT COUNT(*) + 1 as rank FROM stats WHERE score > %s", (s['score'],))
            rank_val = f"#{cur.fetchone()['rank']}"

        # Calculate Group Rank
        g_rank = "N/A"
        if update.effective_chat.type != 'private' and s:
            cur.execute("SELECT COUNT(*) + 1 as rank FROM group_stats WHERE chat_id = %s AND score > %s", 
                        (update.effective_chat.id, s['score']))
            g_rank = f"#{cur.fetchone()['rank']}"

    if not s: return await update.message.reply_text("❌ *No stats found. Play a quiz first!*")

    wrong = s['attempted'] - s['correct']
    accuracy = (s['correct'] / s['attempted'] * 100) if s['attempted'] > 0 else 0
    
    text = (
        "📊 *Detailed Performance Stats*\n\n"
        f"📘 Total Attempts: {s['attempted']}\n"
        f"✅ Correct: {s['correct']}\n"
        f"❌ Wrong: {wrong}\n"
        f"🎯 Accuracy: {accuracy:.2f}%\n"
        f"🔥 Best Streak: {s['max_streak']}\n\n"
        f"🌞 Current Streak: {s['current_streak']}\n"
        f"🏆 Lifetime Score: {s['score']}\n\n"
        f"🌍 Global Rank: {rank_val}\n"
        f"👥 Group Rank: {g_rank}"
    )
    await update.message.reply_text(apply_footer(text))

# 5. COMP_TOGGLE
async def comp_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private': return
    # Admin check for the group
    member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    if member.status not in ['administrator', 'creator'] and update.effective_user.id != OWNER_ID: return

    if not context.args: return await update.message.reply_text("❌ Usage: /comp_toggle <on/off>")
    
    choice = context.args[0].lower()
    val = 1 if choice == 'on' else 0
    with db.get_db() as cur:
        cur.execute("INSERT INTO group_settings (chat_id, compliments_enabled) VALUES (%s, %s) "
                    "ON CONFLICT (chat_id) DO UPDATE SET compliments_enabled = EXCLUDED.compliments_enabled", 
                    (update.effective_chat.id, val))
    await update.message.reply_text(f"✅ Compliments turned *{choice.upper()}* for this group.")


async def nightly_leaderboard_job(context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_leaderboard_data(limit=10)
    if not rows: return
    
    text = "🏆 *Nightly Global Leaderboard (Top 10)*\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. *{r['first_name']}* — {r['score']} pts\n"
    
    # Send to all groups in the database
    with db.get_db() as cur:
        cur.execute("SELECT chat_id FROM chats")
        chats = cur.fetchall()
        for chat in chats:
            try: await context.bot.send_message(chat_id=chat['chat_id'], text=apply_footer(text))
            except: continue
                

# ---------------- MAIN APP ----------------

if __name__ == '__main__':
    db.init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).defaults(defaults).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("randomquiz", send_random_quiz))
    app.add_handler(CommandHandler("myscore", myscore))
    app.add_handler(CommandHandler("mystats", mystats))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("groupleaderboard", groupleaderboard))
    app.add_handler(CommandHandler("addadmin", add_admin))
    app.add_handler(CommandHandler("addquestion", addquestion))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("setcomp", set_compliment))
    app.add_handler(MessageHandler(filters.Document.ALL, addquestion))
    app.add_handler(PollAnswerHandler(handle_poll_answer))
    app.add_handler(CommandHandler("footer", footer_cmd))
    app.add_handler(CommandHandler("autoquiz", autoquiz))
    app.add_handler(CommandHandler("addcompliment", addcompliment))
    app.add_handler(CommandHandler("listcompliments", listcompliments))
    app.add_handler(CommandHandler("delcompliment", delcompliment))
    app.add_handler(CommandHandler("adminlist", adminlist))
    # Admin & Management Handlers
    app.add_handler(CommandHandler("removeadmin", remove_admin))
    app.add_handler(CommandHandler("questions", questions_stats))

        # Stats & Management Handlers
    app.add_handler(CommandHandler("botstats", bot_stats_cmd))
    app.add_handler(CommandHandler("comp_toggle", comp_toggle))

    
    # Job Queue
    jq = app.job_queue
    interval_min = 30
    try:
        with db.get_db() as cur:
            cur.execute("SELECT value FROM settings WHERE key='autoquiz_interval'")
            res = cur.fetchone()
            if res: interval_min = int(res['value'])
    except: pass
        
    jq.run_repeating(auto_quiz_job, interval=interval_min * 60, first=20)


        # Add this line near your other job schedules
    jq.run_daily(nightly_leaderboard_job, time=time(hour=21, minute=0, second=0))

    
    print("🚀 NEETIQBot Master is Online on Render!")
    app.run_polling()
  
  
