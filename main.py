import logging
import asyncio
import pytz 
import html
from html import escape
from telegram.constants import ParseMode
from datetime import datetime, time
from telegram.error import Forbidden, BadRequest
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    PollAnswerHandler,
    MessageHandler,
    filters,
    Defaults
)
import database as db


# ---------------- CONFIG ----------------
# Replace with your actual Bot Token
import os

# --- CONFIGURATION (Environment Variables) ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "6435499094"))
SOURCE_GROUP_ID = int(os.environ.get("SOURCE_GROUP_ID", "-1003729584653"))

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Professional Defaults (MarkdownV2 for cleaner text)
# Note: Using standard Markdown for simplicity to avoid escape errors
defaults = Defaults(parse_mode="Markdown")

# ---------------- HELPERS ----------------
MAX_MESSAGE_LENGTH = 4000  # Safe limit

def split_message(text, max_length=MAX_MESSAGE_LENGTH):
    return [
        text[i:i + max_length]
        for i in range(0, len(text), max_length)
    ]

def apply_footer(text: str) -> str:
    """Applies the professional divider and custom footer text."""
    with db.get_db() as conn:
        f_row = conn.execute("SELECT value FROM settings WHERE key='footer_text'").fetchone()
        f_en = conn.execute("SELECT value FROM settings WHERE key='footer_enabled'").fetchone()
    
    footer_text = f_row[0] if f_row else "NEETIQBot"
    enabled = f_en[0] if f_en else "1"
    
    if enabled == '1':
        return f"{text}\n\n━━━━━━━━━━━━━━━━━━━\n{footer_text}"
    return text

async def is_admin(user_id: int) -> bool:
    """Check if a user has admin privileges or is the owner."""
    if user_id == OWNER_ID:
        return True
    with db.get_db() as conn:
        res = conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone()
        return res is not None

# Constants for Force Sub
CHANNELS = ["@NEETIQBOTUPDATES", "@SANSKAR279"]
INVITE_LINKS = {
    "@NEETIQBOTUPDATES": "https://t.me/NEETIQBOTUPDATES",
    "@SANSKAR279": "https://t.me/SANSKAR279"
}

async def check_subscription(user_id, bot):
    """Returns True if user is in all required channels."""
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            # If bot is not admin in channel, this might fail
            return False
    return True

def get_sub_keyboard():
    """Generates the subscription keyboard."""
    buttons = [
        [InlineKeyboardButton("📢 Join Updates", url=INVITE_LINKS["@NEETIQBOTUPDATES"])],
        [InlineKeyboardButton("💎 Join SANSKAR", url=INVITE_LINKS["@SANSKAR279"])],
        [InlineKeyboardButton("🔄 Verify Joined", callback_data="verify_sub")]
    ]
    return InlineKeyboardMarkup(buttons)

async def verify_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Check if they actually joined now
    if await check_subscription(user_id, context.bot):
        await query.answer("✅ Verification successful! Welcome back.", show_alert=True)
        # Delete the "Join Channel" message to clean up the chat
        await query.message.delete()
        # Re-trigger the start command to show the welcome message
        await start(update, context) 
    else:
        # Show an alert if they still haven't joined
        await query.answer("❌ You still haven't joined both channels!", show_alert=True)
		
		
# ---------------- REGISTRATION ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    # 1. Force Subscription Check
    # Users must be in the channels to use the bot in private
    if chat.type == 'private':
        if not await check_subscription(user.id, context.bot):
            return await update.message.reply_text(
                "⚠️ <b>Access Denied!</b>\n\nYou must join our official channels to use NEETIQBot. "
                "Click the buttons below to join, then click <b>Verify Joined</b>.",
                reply_markup=get_sub_keyboard(),
                parse_mode="HTML"
            )

    # 2. Database Registration (User & Group)
    safe_name = html.escape(user.first_name)
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

    # 3. Welcome Messages
    if chat.type == 'private':
        welcome = (
            f"👋 <b>Welcome to NEETIQBot, {safe_name}!</b>\n\n"
            "I am your dedicated NEET preparation assistant. "
            "I provide high-quality MCQs, track your streaks, and manage competitive leaderboards.\n\n"
            "📌 <b>Use</b> /help <b>to see all available commands.</b>"
        )
        bot_username = context.bot.username
        btn = [[InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{bot_username}?startgroup=true")]]
        
        await update.message.reply_text(
            apply_footer(welcome), 
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode="HTML"
        )
    else:
        safe_title = html.escape(chat.title) if chat.title else "Group"
        group_msg = f"🎉 <b>Group successfully registered with NEETIQBot!</b>\n\nPreparing <b>{safe_title}</b> for upcoming quizzes."
        await update.message.reply_text(apply_footer(group_msg), parse_mode="HTML")
		
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 <b>NEETIQBot Command List</b>\n\n"
        "👋 <b>Basic Commands</b>\n"
        "<code>/start</code> - Register and start the bot\n"
        "<code>/help</code> - Display this help manual\n\n"
        "📘 <b>Quiz System</b>\n"
        "<code>/randomquiz</code> - Receive a random NEET MCQ\n"
        "<code>/myscore</code> - View your point summary\n"
        "<code>/mystats</code> - Detailed performance analysis\n\n"
        "🏆 <b>Leaderboards</b>\n"
        "<code>/leaderboard</code> - Global rankings (Top 25)\n"
        "<code>/groupleaderboard</code> - Group specific rankings"
    )

    # Creating the Inline Button for Support
    keyboard = [
        [InlineKeyboardButton("⚒️ NEETIQbot Support ", url="https://t.me/NEETIQsupportbot")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        apply_footer(help_text), 
        reply_markup=reply_markup,
        parse_mode="HTML"
	)
	

# ---------------- QUIZ SYSTEM ----------------

async def send_random_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a random NEET MCQ and permanently deletes it from the DB to prevent repetition."""
    chat_id = update.effective_chat.id
    
    with db.get_db() as conn:
        # 1. Fetch any random question currently in the database
        q = conn.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT 1").fetchone()

    if not q:
        # No need to reset sent_questions because we are deleting questions permanently
        return await update.message.reply_text(
            "📭 *Database Empty!* All questions have been used and deleted. "
            "Please upload new questions using /addquestion."
        )

    options = [q['a'], q['b'], q['c'], q['d']]
    
    # Map correct answer (supports 1-4 or A-D)
    correct_map = {'1': 0, '2': 1, '3': 2, '4': 3, 'A': 0, 'B': 1, 'C': 2, 'D': 3}
    c_idx = correct_map.get(str(q['correct']).upper(), 0)

    try:
        # 2. Send the Poll
        msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"🧠 NEET MCQ:\n\n{q['question']}",
            options=options,
            type=Poll.QUIZ,
            correct_option_id=c_idx,
            explanation=f"📖 Explanation:\n{q['explanation']}",
            is_anonymous=False
        )
        
        # 3. Track poll for answers and IMMEDIATELY delete the question
        with db.get_db() as conn:
            # Save poll info so /myscore works
            conn.execute("INSERT INTO active_polls VALUES (?,?,?)", (msg.poll.id, chat_id, c_idx))
            
            # Delete the question by ID so it can never be sent again
            conn.execute("DELETE FROM questions WHERE id = ?", (q['id'],))
            
    except Exception as e:
        logger.error(f"Error in Quiz Flow: {e}")
        await update.message.reply_text("❌ Failed to process the quiz. Please check database logs.")

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes answer and updates subject-specific stats."""
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user  
    
    if not user:
        return
        
    user_id = user.id
    username = user.username
    first_name = user.first_name

    # 1. Sync User and Fetch Poll Data (including subject)
    with db.get_db() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
        """, (user_id, username, first_name))
        
        # We now SELECT 'subject' as well
        poll_data = conn.execute(
            "SELECT chat_id, correct_option_id, subject FROM active_polls WHERE poll_id = ?", 
            (poll_id,)
        ).fetchone()

    if not poll_data:
        return

    chat_id = poll_data[0]
    correct_option = poll_data[1]
    subject = poll_data[2] # Biology, Physics, or Chemistry
    
    is_correct = (len(answer.option_ids) > 0 and answer.option_ids[0] == correct_option)

    # 2. Update Stats (Now passing the subject)
    db.update_user_stats(
        user_id, 
        chat_id, 
        is_correct, 
        subject=subject, 
        username=username, 
        first_name=first_name
    )

    # 3. Compliment Logic (Remains the same)
    with db.get_db() as conn:
        setting = conn.execute(
            "SELECT compliments_enabled FROM group_settings WHERE chat_id = ?", 
            (chat_id,)
        ).fetchone()
        
        if setting and setting[0] == 0:
            return

        c_type = "correct" if is_correct else "wrong"
        comp = conn.execute(
            "SELECT text FROM group_compliments WHERE chat_id = ? AND type = ? ORDER BY RANDOM() LIMIT 1",
            (chat_id, c_type)
        ).fetchone()

        if not comp:
            comp = conn.execute(
                "SELECT text FROM compliments WHERE type = ? ORDER BY RANDOM() LIMIT 1",
                (c_type,)
            ).fetchone()

    if comp:
        compliment_text = comp[0]
        safe_name = html.escape(first_name)
        
        if username:
            mention_name = f"<b>@{html.escape(username)}</b>"
        else:
            mention_name = f'<b><a href="tg://user?id={user_id}">{safe_name}</a></b>'
            
        final_text = compliment_text.replace("{user}", mention_name)

        if chat_id < 0: # Only send compliments in groups
            try:
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=final_text, 
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Error sending compliment: {e}")


# ---------------- PERFORMANCE STATS ----------------

async def myscore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a quick summary of the user's current score."""
    user = update.effective_user
    with db.get_db() as conn:
        s = conn.execute("SELECT * FROM stats WHERE user_id = ?", (user.id,)).fetchone()
    
    if not s:
        return await update.message.reply_text("❌ *No data found.* Participate in a quiz to generate stats!")

    text = (
        "📊 *Your Score Summary*\n\n"
        f"Total Attempted: `{s['attempted']}`\n"
        f"Correct Answers: `{s['correct']}`\n"
        f"Incorrect Answers: `{s['attempted'] - s['correct']}`\n"
        f"Current Score: `{s['score']}`"
    )
    await update.message.reply_text(apply_footer(text))


async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    chat_id = chat.id

    with db.get_db() as conn:
        # Fetching stats; using indices for broad compatibility
        s = conn.execute("SELECT user_id, attempted, correct, score, current_streak, max_streak FROM stats WHERE user_id = ?", (user.id,)).fetchone()
        
        if not s:
            return await update.message.reply_text("❌ <b>No statistics found!</b>\nAnswer some quizzes to generate your profile.", parse_mode="HTML")

        # Column mapping for clarity based on your query
        # (user_id:0, attempted:1, correct:2, score:3, current_streak:4, max_streak:5)
        attempted = s[1]
        correct = s[2]
        score = s[3]
        c_streak = s[4]
        m_streak = s[5]

        # Calculate Global Rank
        g_rank_row = conn.execute("SELECT COUNT(*) + 1 FROM stats WHERE score > ?", (score,)).fetchone()
        global_rank = g_rank_row[0]

        # Calculate Group Rank (only if in a group)
        group_rank = "N/A"
        if chat.type != 'private':
            # Note: This assumes you have a 'group_stats' table or column sync
            gr_row = conn.execute("SELECT COUNT(*) + 1 FROM group_stats WHERE chat_id = ? AND score > ?",
                                 (chat_id, score)).fetchone()
            group_rank = gr_row[0] if gr_row else "N/A"

    # 1. Performance Logic (NEET Scoring: +4, -1)
    accuracy = (correct / attempted * 100) if attempted > 0 else 0
    wrong = attempted - correct
    xp = (correct * 4) - (wrong * 1)
    xp = max(0, xp)  # XP cannot be negative

    # 2. Dynamic Rank Titles (Visual Redesign)
    if xp > 1000: rank_title = "🏥 AIIMS Dean"
    elif xp > 500: rank_title = "👨‍⚕️ Senior Consultant"
    elif xp > 300: rank_title = "💉 Resident Doctor"
    elif xp > 150: rank_title = "🩺 Gold Intern"
    elif xp > 50:  rank_title = "📚 Elite Aspirant"
    else:          rank_title = "🧬 Medical Student"

    # 3. HTML Profile Construction
    divider = "<b>━━━━━━━━━━━━━━━━━━━━</b>"
    safe_name = html.escape(user.first_name)

    text = (
        f"🪪 <b>NEETIQ USER PROFILE</b>\n"
        f"{divider}\n"
        f"👤 <b>NAME</b> : <code>{safe_name}</code>\n"
        f"🏅 <b>RANK</b> : <b>{rank_title}</b>\n"
        f"{divider}\n"
        f"📊 <b>POSITION DATA</b>\n"
        f"<code>╭────────────────────</code>\n"
        f"<code>│ 🏆 Global  : #{global_rank}</code>\n"
        f"<code>│ 👥 Group   : #{group_rank}</code>\n"
        f"<code>│ 🧬 Total XP: {xp:,}</code>\n"
        f"<code>╰────────────────────</code>\n\n"
        f"📈 <b>ACCURACY TRACKER</b>\n"
        f"<code>┌── Attempted : {attempted}</code>\n"
        f"<code>├── Correct   : {correct}</code>\n"
        f"<code>└── Precision : {accuracy:.1f}%</code>\n\n"
        f"🔥 <b>STREAK MONITOR</b>\n"
        f"<code>┌── Current   : {c_streak}</code>\n"
        f"<code>└── Best      : {m_streak}</code>\n"
        f"{divider}"
    )

    await update.message.reply_text(
        apply_footer(text), 
        parse_mode="HTML",
        disable_web_page_preview=True
	)
	


# ---------------- LEADERBOARD helper ----------------
# Helper for visual rank badges
def get_rank_icon(rank):
    if rank == 1: return "🥇"
    if rank == 2: return "🥈"
    if rank == 3: return "🥉"
    return f"<code>{rank:02d}.</code>"

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redesigned Global Leaderboard: Uniform format for all ranks."""
    try:
        # Fetch top 10 rows
        rows = db.get_leaderboard_data(limit=10) 
        
        if not rows:
            return await update.message.reply_text("<b>📭 The Global Arena is currently empty!</b>", parse_mode="HTML")

        divider = "<b>━━━━━━━━━━━━━━━━━━━━</b>"
        text = (
            "🏆 <b>NEETIQ GLOBAL CHAMPIONS</b>\n"
            f"{divider}\n\n"
        )

        for i, r in enumerate(rows, 1):
            icon = get_rank_icon(i) # e.g., 🥇, 🥈, 🥉, or 04.
            name = html.escape(str(r[0]))
            points = r[3]
            
            # Consistent format: User - x pts!
            text += f"{icon} {name} - {points:,} pts!\n"

        text += f"\n{divider}"
        
        await update.message.reply_text(
            apply_footer(text), 
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"Leaderboard Error: {e}")
        await update.message.reply_text("❌ <b>Failed to sync Global Rankings.</b>", parse_mode="HTML")
			

async def groupleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redesigned Group Leaderboard with specialized header."""
    if update.effective_chat.type == 'private':
        return await update.message.reply_text("❌ <b>This command only works inside Groups!</b>", parse_mode="HTML")

    try:
        chat_id = update.effective_chat.id
        rows = db.get_leaderboard_data(chat_id=chat_id, limit=10)
        title = html.escape(update.effective_chat.title or "Group")
        
        divider = "<b>━━━━━━━━━━━━━━━━━━━━</b>"
        text = (
            f"👥 <b>{title.upper()} CHAMPIONS</b>\n"
            f"{divider}\n\n"
        )

        if not rows:
            text += "<i>No participants recorded yet. Start a quiz to claim the first spot!</i>\n"
        else:
            for i, r in enumerate(rows, 1):
                icon = get_rank_icon(i)
                name = html.escape(str(r[0]))
                points = r[3]
                
                # Compact style for groups to keep chat clutter low
                text += f"{icon} {name} — <b>{points:,} pts</b>\n"

        text += f"\n{divider}"

        await update.message.reply_text(
            apply_footer(text), 
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"Group LB Error: {e}")
        await update.message.reply_text("❌ <b>Error loading group stats.</b>", parse_mode="HTML")
		



# ---------------- ADMIN MANAGEMENT ----------------

async def adminlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all authorized admins."""
    if not await is_admin(update.effective_user.id): return
    with db.get_db() as conn:
        admins = conn.execute("SELECT user_id FROM admins").fetchall()
    
    text = "👮 *Authorized Admins:*\n\n"
    text += f"• `{OWNER_ID}` (Owner)\n"
    for adm in admins:
        if adm[0] != OWNER_ID:
            text += f"• `{adm[0]}`\n"
    await update.message.reply_text(apply_footer(text))

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        new_id = int(context.args[0])
        with db.get_db() as conn:
            conn.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?,?)", 
                         (new_id, str(datetime.now())))
        await update.message.reply_text(f"✅ User `{new_id}` is now an Admin.")
    except:
        await update.message.reply_text("❌ Usage: `/addadmin <user_id>`")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        rem_id = int(context.args[0])
        with db.get_db() as conn:
            conn.execute("DELETE FROM admins WHERE user_id = ?", (rem_id,))
        await update.message.reply_text(f"✅ User `{rem_id}` removed from Admin list.")
    except:
        await update.message.reply_text("❌ Usage: `/removeadmin <user_id>`")

# ---------------- QUESTION MANAGEMENT ----------------
async def addquestion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds questions with subject detection (Bio/Phy/Che)."""
    if not await is_admin(update.effective_user.id): return
    
    content = ""
    if update.message.document and update.message.document.file_name.endswith('.txt'):
        file = await context.bot.get_file(update.message.document.file_id)
        content = (await file.download_as_bytearray()).decode('utf-8')
    elif update.message.text:
        content = update.message.text.replace("/addquestion", "").strip()

    if not content:
        return await update.message.reply_text("❌ Please provide text or a .txt file.")

    raw_entries = [e.strip() for e in content.split('\n\n') if e.strip()]
    added_count = 0
    skipped_count = 0

    with db.get_db() as conn:
        for entry in raw_entries:
            lines = [l.strip() for l in entry.split('\n') if l.strip()]
            
            if len(lines) >= 7:
                try:
                    explanation = lines[-1]
                    correct = str(lines[-2]).strip().upper()
                    opt_d = lines[-3]
                    opt_c = lines[-4]
                    opt_b = lines[-5]
                    opt_a = lines[-6]
                    full_q_text = "\n".join(lines[:-6])

                    # --- SUBJECT DETECTION LOGIC ---
                    subject = "General"
                    clean_q_text = full_q_text
                    
                    if full_q_text.lower().startswith("biology:"):
                        subject = "Biology"
                        clean_q_text = full_q_text[8:].strip()
                    elif full_q_text.lower().startswith("physics:"):
                        subject = "Physics"
                        clean_q_text = full_q_text[8:].strip()
                    elif full_q_text.lower().startswith("chemistry:"):
                        subject = "Chemistry"
                        clean_q_text = full_q_text[10:].strip()

                    if correct not in ['1', '2', '3', '4', 'A', 'B', 'C', 'D']:
                        skipped_count += 1
                        continue

                    # Insert with the new 'subject' column
                    conn.execute(
                        "INSERT INTO questions (question, a, b, c, d, correct, explanation, subject) VALUES (?,?,?,?,?,?,?,?)",
                        (clean_q_text, opt_a, opt_b, opt_c, opt_d, correct, explanation, subject)
                    )
                    added_count += 1
                except Exception as e:
                    logger.error(f"Error adding question: {e}")
                    skipped_count += 1
            else:
                skipped_count += 1

    await update.message.reply_text(apply_footer(f"📊 *Import Summary:*\n✅ Added: `{added_count}`\n⚠️ Skipped: `{skipped_count}`"))
	

async def questions_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays total questions broken down by subject."""
    if not await is_admin(update.effective_user.id): return
    
    with db.get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        bio = conn.execute("SELECT COUNT(*) FROM questions WHERE subject='Biology'").fetchone()[0]
        phy = conn.execute("SELECT COUNT(*) FROM questions WHERE subject='Physics'").fetchone()[0]
        che = conn.execute("SELECT COUNT(*) FROM questions WHERE subject='Chemistry'").fetchone()[0]
        gen = conn.execute("SELECT COUNT(*) FROM questions WHERE subject='General'").fetchone()[0]

    stats_msg = (
        "📘 <b>Question Bank Overview</b>\n\n"
        f"🧬 <b>Biology:</b> <code>{bio}</code>\n"
        f"⚡ <b>Physics:</b> <code>{phy}</code>\n"
        f"🧪 <b>Chemistry:</b> <code>{che}</code>\n"
        f"📝 <b>General/Other:</b> <code>{gen}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Total Questions:</b> <code>{total}</code>"
    )
    await update.message.reply_text(apply_footer(stats_msg), parse_mode="HTML")


async def del_all_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("⛔ Unauthorized.")

    try:
        # Correct the name here to match the DB file exactly
        db.delete_all_questions() 
        
        await update.message.reply_text("🗑️ Questions deleted!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ---------------- COMPLIMENT MANAGEMENT ----------------

async def addcompliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id): return
    try:
        c_type = context.args[0].lower() # 'correct' or 'wrong'
        text = " ".join(context.args[1:])
        if c_type not in ['correct', 'wrong']: raise ValueError
        with db.get_db() as conn:
            conn.execute("INSERT INTO compliments (type, text) VALUES (?,?)", (c_type, text))
        await update.message.reply_text(f"✅ Added {c_type} compliment: \"{text}\"")
    except:
        await update.message.reply_text("❌ *Usage:* `/addcompliment correct Well done {user}!`")

async def listcompliments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        return

    with db.get_db() as conn:
        rows = conn.execute("SELECT * FROM compliments").fetchall()

    if not rows:
        await update.message.reply_text("📭 No compliments added yet.")
        return

    text = "📝 Compliment List:\n\n"

    for r in rows:
        text += (
            f"ID: {r['id']} | Type: {r['type']}\n"
            f"Text: {r['text']}\n\n"
        )

    chunks = split_message(text)

    for chunk in chunks:
        await update.message.reply_text(chunk)

async def delcompliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id): return
    try:
        cid = int(context.args[0])
        with db.get_db() as conn:
            conn.execute("DELETE FROM compliments WHERE id = ?", (cid,))
        await update.message.reply_text(f"✅ Compliment ID `{cid}` deleted.")
    except:
        await update.message.reply_text("❌ Usage: `/delcompliment <id>`")

async def delallcompliments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes all compliments. Restricted to Owner."""
    # Ensure OWNER_ID is defined in your script
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("⛔ *Unauthorized:* Only the owner can wipe compliments.")

    try:
        # Call it directly from the imported 'db' module
        db.delete_all_compliments() 
        
        await update.message.reply_text("🗑️ *Compliments Cleared:* The database table is now empty.")
    except Exception as e:
        await update.message.reply_text(f"❌ *Error:* {e}")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcasts with selection buttons and exact formatting preservation."""
    if not await is_admin(update.effective_user.id): return

    # Capture the message with HTML formatting preserved
    if update.message.reply_to_message:
        broadcast_msg = update.message.reply_to_message.text_html
    else:
        # Removes the command '/broadcast' but keeps all other formatting/spacing
        broadcast_msg = update.message.text_html.split(None, 1)[1] if len(update.message.text.split()) > 1 else ""

    if not broadcast_msg:
        return await update.message.reply_text(
            "❌ <b>Error:</b> Please provide text or reply to a message.\n"
            "Usage: <code>/broadcast Your Message</code>", 
            parse_mode="HTML"
        )

    # Store message in memory for the button click
    context.user_data['pending_bc'] = broadcast_msg

    buttons = [
        [InlineKeyboardButton("👤 Users", callback_data="bc_users"),
         InlineKeyboardButton("👥 Groups", callback_data="bc_groups")],
        [InlineKeyboardButton("🌍 Both (Users + Groups)", callback_data="bc_both")],
        [InlineKeyboardButton("❌ Cancel", callback_data="bc_cancel")]
    ]
    
    await update.message.reply_text(
        f"📢 <b>BROADCAST PREVIEW:</b>\n\n{broadcast_msg}\n\n<b>Where should I send this?</b>",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML"
    )

async def broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the selection and sends the formatted message."""
    query = update.callback_query
    action = query.data
    
    if action == "bc_cancel":
        context.user_data.pop('pending_bc', None)
        return await query.edit_message_text("❌ Broadcast cancelled.")

    msg = context.user_data.get('pending_bc')
    if not msg:
        return await query.answer("❌ Data lost. Send /broadcast again.", show_alert=True)

    await query.edit_message_text("🚀 <b>Broadcasting...</b>", parse_mode="HTML")

    targets = []
    with db.get_db() as conn:
        if action in ["bc_users", "bc_both"]:
            targets.extend([r[0] for r in conn.execute("SELECT user_id FROM users").fetchall()])
        if action in ["bc_groups", "bc_both"]:
            targets.extend([r[0] for r in conn.execute("SELECT chat_id FROM chats").fetchall()])

    # Remove duplicates and send
    targets = list(set(targets))
    success, fail = 0, 0

    for t_id in targets:
        try:
            # text_html is key here to keep your spacing and bolding
            await context.bot.send_message(chat_id=t_id, text=msg, parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05) # Prevent flood limits
        except Exception:
            fail += 1

    await query.message.reply_text(
        f"✅ <b>Broadcast Finished</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎯 Success: <code>{success}</code>\n"
        f"⚠️ Failed: <code>{fail}</code>",
        parse_mode="HTML"
    )
    context.user_data.pop('pending_bc', None)


async def scorecard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    # --- PRIVATE CHAT CHECK ---
    if chat.type != 'private':
        # Optional: You can send a message or just return. 
        # Here we reply with a tip to use the bot in DM.
        return await update.message.reply_text(
            "❌ <b>Access Denied!</b>\n\nFor privacy reasons, your detailed scorecard can only be viewed in a private chat with the bot.",
            parse_mode="HTML"
        )

    with db.get_db() as conn:
        # Fetch stats from the updated columns
        s = conn.execute("SELECT * FROM stats WHERE user_id = ?", (user.id,)).fetchone()
    
    if not s:
        return await update.message.reply_text("❌ <b>No data found!</b> Start solving quizzes to see your progress.", parse_mode="HTML")

    # Helper function to calculate accuracy safely
    def get_acc(cor, att):
        return round((cor / att * 100), 1) if att > 0 else 0

    # Calculating accuracies
    bio_acc = get_acc(s['bio_cor'], s['bio_att'])
    phy_acc = get_acc(s['phy_cor'], s['phy_att'])
    che_acc = get_acc(s['che_cor'], s['che_att'])

    # Formatting the Scorecard
    scorecard_msg = (
        f"🪪 <b>NEETIQ USER SCORECARD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>NAME :</b> {html.escape(user.first_name)}\n"
        f"🏅 <b>RANK :</b> <b>Aspirant</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>POSITION & PROGRESS</b>\n"
        f"<code>╭────────────────────</code>\n"
        f"<code>│ 🏆 Global  : #Rank</code>\n" 
        f"<code>│ 👥 Group   : #Rank</code>\n"
        f"<code>│ 🧬 Total XP: {s['score']}</code>\n"
        f"<code>╰────────────────────</code>\n\n"
        f"📊 <b>SUBJECT PERFORMANCE</b>\n"
        f"<code>╭────────────────────</code>\n"
        f"<code>│ 🧬 BIO : {s['bio_cor']}/{s['bio_att']}</code>\n"
        f"<code>│ ⚡ PHY : {s['phy_cor']}/{s['phy_att']}</code>\n"
        f"<code>│ 🧪 CHE : {s['che_cor']}/{s['che_att']}</code>\n"
        f"<code>╰────────────────────</code>\n\n"
        f"📈 <b>ACCURACY TRACKER</b>\n"
        f"<code>╭────────────────────</code>\n" 
        f"<code>│ 🧬 BIO : {bio_acc}%</code>\n"
        f"<code>│ ⚡ PHY : {phy_acc}%</code>\n"
        f"<code>│ 🧪 CHE : {che_acc}%</code>\n"
        f"<code>╰────────────────────</code>\n\n"
        f"🔥 <b>STREAK MONITOR</b>\n"
        f"<code>╭────────────────────</code>\n" 
        f"<code>┌.   Current   : {s['current_streak']}</code>\n"
        f"<code>└.     Best      : {s['max_streak']}</code>\n"
        f"<code>╰────────────────────</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>NEETIQbot</b>"
    )

    await update.message.reply_text(scorecard_msg, parse_mode="HTML")


# ---------------- SETTINGS (FOOTER & AUTOQUIZ) ----------------

async def footer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manages the message footer status and text."""
    if not await is_admin(update.effective_user.id): return
    args = context.args
    
    if not args:
        return await update.message.reply_text(
            "⚙️ *Footer Settings Help:*\n"
            "• `/footer on` - Enable footer\n"
            "• `/footer off` - Disable footer\n"
            "• `/footer <text>` - Set custom footer text"
        )

    with db.get_db() as conn:
        if args[0].lower() == 'on':
            conn.execute("UPDATE settings SET value='1' WHERE key='footer_enabled'")
            await update.message.reply_text("✅ *Footer is now Enabled.*")
        elif args[0].lower() == 'off':
            conn.execute("UPDATE settings SET value='0' WHERE key='footer_enabled'")
            await update.message.reply_text("❌ *Footer is now Disabled.*")
        else:
            new_text = " ".join(args)
            conn.execute("UPDATE settings SET value=? WHERE key='footer_text'", (new_text,))
            await update.message.reply_text(f"✅ *Footer text updated to:* `{new_text}`")

async def autoquiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manages the automatic quiz scheduler."""
    if not await is_admin(update.effective_user.id): return
    args = context.args
    
    if not args:
        return await update.message.reply_text(
            "⚙️ *AutoQuiz Settings Help:*\n"
            "• `/autoquiz on` - Start automatic quizzes\n"
            "• `/autoquiz off` - Stop automatic quizzes\n"
            "• `/autoquiz interval <min>` - Set time interval (minutes)"
        )

    with db.get_db() as conn:
        if args[0].lower() == 'on':
            conn.execute("UPDATE settings SET value='1' WHERE key='autoquiz_enabled'")
            await update.message.reply_text("✅ *Auto Quiz mode is now ON.*")
        elif args[0].lower() == 'off':
            conn.execute("UPDATE settings SET value='0' WHERE key='autoquiz_enabled'")
            await update.message.reply_text("❌ *Auto Quiz mode is now OFF.*")
        elif args[0].lower() == 'interval' and len(args) > 1:
            try:
                minutes = int(args[1])
                conn.execute("UPDATE settings SET value=? WHERE key='autoquiz_interval'", (str(minutes),))
                await update.message.reply_text(f"✅ *Quiz interval set to {minutes} minutes.*")
            except ValueError:
                await update.message.reply_text("❌ Please provide a valid number for minutes.")

async def auto_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    """Picks ONE question and sends it to ALL groups simultaneously with HTML formatting."""
    with db.get_db() as conn:
        # 1. Check if auto-quiz is enabled
        setting = conn.execute("SELECT value FROM settings WHERE key='autoquiz_enabled'").fetchone()
        if not setting or setting[0] == '0': 
            return
        
        # 2. Pick a random question
        # Fetching by index to ensure compatibility: id:0, question:1, a:2, b:3, c:4, d:5, correct:6, explanation:7
        q = conn.execute("SELECT id, question, a, b, c, d, correct, explanation FROM questions ORDER BY RANDOM() LIMIT 1").fetchone()
        
        if not q:
            return 

        # 3. Get all active groups
        chats = conn.execute("SELECT chat_id FROM chats WHERE type != 'private'").fetchall()

    # Prep Poll Data
    options = [str(q[2]), str(q[3]), str(q[4]), str(q[5])]
    correct_map = {'1': 0, '2': 1, '3': 2, '4': 3, 'A': 0, 'B': 1, 'C': 2, 'D': 3}
    c_idx = correct_map.get(str(q[6]).upper(), 0)

    divider = "<b>━━━━━━━━━━━━━━━━━</b>"
    question_text = f"🧠 <b>NEET MCQ (Global Quiz)</b>\n{divider}\n\n{q[1]}"
    explanation_text = f"📖 <b>Explanation:</b>\n{q[7]}"

    # Send to all groups
    for c in chats:
        try:
            msg = await context.bot.send_poll(
                chat_id=c[0],
                question=question_text,
                options=options,
                type=Poll.QUIZ,
                correct_option_id=c_idx,
                explanation=explanation_text,
                explanation_parse_mode=ParseMode.HTML,
                is_anonymous=False
            )
            
            # Register active poll for scoring
            with db.get_db() as conn:
                conn.execute("INSERT INTO active_polls (poll_id, chat_id, correct_option_id) VALUES (?,?,?)", 
                             (msg.poll.id, c[0], c_idx))
            
            await asyncio.sleep(0.2) 
        except Exception:
            continue

    # 4. Remove question from pool after successful broadcast
    with db.get_db() as conn:
        conn.execute("DELETE FROM questions WHERE id = ?", (q[0],))

async def nightly_leaderboard_job(context: ContextTypes.DEFAULT_TYPE):
    """Sends a daily summary with plain-text names and bold headers."""
    
    # 1. Generate Global List (Plain Text)
    # Using html.escape to prevent formatting errors from user names
    global_rows = db.get_leaderboard_data(limit=10)
    global_list = ""
    if not global_rows:
        global_list = "<i>No global data recorded today.</i>\n"
    else:
        for i, r in enumerate(global_rows, 1):
            badge = get_rank_icon(i) # Your icon function
            name = html.escape(str(r[0]))
            # Points formatted with commas for readability
            global_list += f"{badge} {name} - {r[3]:,} pts\n"

    # 2. Get Group List
    with db.get_db() as conn:
        chats = conn.execute("SELECT chat_id, title FROM chats WHERE type != 'private'").fetchall()

    # 3. Process each group
    for c in chats:
        chat_id = c[0]
        # Ensure the group title is safe for HTML
        raw_title = c[1] if c[1] else "This Group"
        safe_title = html.escape(raw_title)
        
        try:
            group_rows = db.get_leaderboard_data(chat_id=chat_id, limit=10)
            group_list = ""

            if not group_rows:
                group_list = "<i>No participants in this group yet.</i>\n"
            else:
                for i, r in enumerate(group_rows, 1):
                    # FIX: Changed get_badge to get_rank_icon to match your code
                    badge = get_rank_icon(i) 
                    name = html.escape(str(r[0]))
                    group_list += f"{badge} {name} - {r[3]:,} pts\n"

            divider = "<b>━━━━━━━━━━━━━━━━━━━━</b>"
            final_message = (
                "🌙 <b>DAILY LEADERBOARD</b>\n"
                f"{divider}\n"
                "🌍 <b>Global Top 10</b>\n"
                f"{global_list}"
                f"{divider}\n"
                f"👥 <b>{safe_title.upper()} Top 10</b>\n"
                f"{group_list}"
                f"{divider}\n"
                "Great effort today, champs! 🚀\nKeep the momentum going!"
            )

            # apply_footer adds your custom footer text
            await context.bot.send_message(
                chat_id=chat_id,
                text=apply_footer(final_message),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
            # Anti-flood delay to prevent Telegram from blocking the bot
            await asyncio.sleep(0.5)
            
        except Exception as e:
            # Logs the error but keeps the loop running for other groups
            print(f"⚠️ Error sending leaderboard to {chat_id}: {e}")
            continue


async def bot_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a high-level overview of the bot's reach and data."""
    if not await is_admin(update.effective_user.id): return
    
    with db.get_db() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_chats = conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0]
        total_questions = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        total_attempts = conn.execute("SELECT SUM(attempted) FROM stats").fetchone()[0] or 0
        total_admins = conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0] + 1 # +1 for Owner
	
    stats_text = (
        "🤖 *NEETIQ Master Bot Statistics*\n\n"
        f"👤 *Total Users:* `{total_users}`\n"
        f"👥 *Total Groups:* `{total_chats}`\n"
        f"👮 *Total Admins:* `{total_admins}`\n\n"
        "📊 *Database Growth*\n"
        f"❓ *Total Questions:* `{total_questions}`\n"
        f"📝 *Total Global Attempts:* `{total_attempts}`\n"
    )
    
    await update.message.reply_text(apply_footer(stats_text))

async def is_telegram_group_admin(update: Update):
    """Checks if the user is an actual admin of the Telegram Group."""
    member = await update.effective_chat.get_member(update.effective_user.id)
    return member.status in ['creator', 'administrator']

async def toggle_compliments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle compliments ON or OFF."""
    # Check if it's a group and if user is admin
    if update.effective_chat.type == "private":
        return await update.message.reply_text("❌ This command only works in groups.")
        
    if not await is_telegram_group_admin(update):
        return await update.message.reply_text("❌ Only group admins can do this.")

    status_input = context.args[0].lower() if context.args else ""
    if status_input not in ['on', 'off']:
        return await update.message.reply_text("📝 Usage: `/comp_toggle on` or `/comp_toggle off`")

    status = 1 if status_input == 'on' else 0
    chat_id = update.effective_chat.id

    with db.get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO group_settings (chat_id, compliments_enabled) VALUES (?, ?)", (chat_id, status))
    
    await update.message.reply_text(f"✅ Compliments are now {'ON' if status else 'OFF'}")

async def set_group_compliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set custom compliment text."""
    if not await is_telegram_group_admin(update):
        return await update.message.reply_text("❌ Only group admins can do this.")

    if len(context.args) < 2:
        return await update.message.reply_text("📝 Usage: `/setcomp correct Great job {user}!`")

    c_type = context.args[0].lower()
    c_text = " ".join(context.args[1:])
    chat_id = update.effective_chat.id

    if c_type not in ['correct', 'wrong']:
        return await update.message.reply_text("❌ Type must be 'correct' or 'wrong'.")

    with db.get_db() as conn:
        # Delete old custom ones for this type in this group first to prevent spam
        conn.execute("DELETE FROM group_compliments WHERE chat_id = ? AND type = ?", (chat_id, c_type))
        conn.execute("INSERT INTO group_compliments VALUES (?, ?, ?)", (chat_id, c_type, c_text))
    
    await update.message.reply_text(f"✅ Custom {c_type} message saved!")


# REPLACE with your actual source group ID
SOURCE_GROUP_ID = -1003729584653 

async def mirror_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Enhanced Mirroring: Supports Photos, PDFs, Stickers, Polls, and Formatted Text.
    """
    # 1. Security Check
    if update.effective_chat.id != SOURCE_GROUP_ID:
        return

    # 2. Skip commands
    if update.message.text and update.message.text.startswith('/'):
        return

    # 3. Get targets from DB
    with db.get_db() as conn:
        user_rows = conn.execute("SELECT user_id FROM users").fetchall()
        group_rows = conn.execute("SELECT chat_id FROM chats WHERE chat_id != ?", (SOURCE_GROUP_ID,)).fetchall()
    
    # Track counts for the final message
    user_ids = [row[0] for row in user_rows]
    group_ids = [row[0] for row in group_rows]
    all_targets = set(user_ids + group_ids)

    print(f"📡 Mirroring content to {len(all_targets)} destinations...")

    user_success = 0
    group_success = 0
    removed = 0

    for target_id in all_targets:
        try:
            # copy_message handles PDFs, Images, and Inline buttons automatically
            await context.bot.copy_message(
                chat_id=target_id,
                from_chat_id=SOURCE_GROUP_ID,
                message_id=update.message.message_id
            )
            
            # Count success based on ID type (Groups usually have negative IDs)
            if str(target_id).startswith('-'):
                group_success += 1
            else:
                user_success += 1
                
            await asyncio.sleep(0.05) 

        except (Forbidden, BadRequest) as e:
            error_msg = str(e)
            if "Forbidden" in error_msg or "Chat not found" in error_msg:
                with db.get_db() as conn:
                    conn.execute("DELETE FROM users WHERE user_id = ?", (target_id,))
                    conn.execute("DELETE FROM chats WHERE chat_id = ?", (target_id,))
                removed += 1
        except Exception as e:
            print(f"❌ Mirror Error for {target_id}: {e}")

    # 4. Send the Congratulations Summary to YOU or the Master Group
    summary = (
        "Congratulations 🎉\n"
        f"Sent to : {group_success} grps and {user_success} users"
    )
    await context.bot.send_message(chat_id=SOURCE_GROUP_ID, text=summary)

import os
from threading import Thread
from flask import Flask

# --- KEEP-ALIVE SERVER FOR RENDER ---
flask_app = Flask('')

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    # Render provides PORT environment variable automatically
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    # 1. Initialize Database
    db.init_db()
    
    # 2. Start the Keep-Alive Web Server
    print("🌐 Starting Keep-Alive server...")
    keep_alive()

    # 3. Define Timezone for Kolkata
    ist_timezone = pytz.timezone('Asia/Kolkata')

    # 4. Build Application using Environment Variables
    # We add the timezone to 'defaults' so all scheduled jobs use IST
    application = (
        ApplicationBuilder()
        .token(os.environ.get("BOT_TOKEN")) 
        .defaults(Defaults(parse_mode=ParseMode.HTML, tzinfo=ist_timezone)) 
        .build()
    )

    # --- HANDLERS ---
    # Mirroring (Place first)
    application.add_handler(MessageHandler(
        filters.Chat(SOURCE_GROUP_ID) & 
        (~filters.COMMAND) & 
        (filters.TEXT | filters.PHOTO | filters.Document.ALL | filters.POLL), 
        mirror_messages
    ))

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("randomquiz", send_random_quiz))
    application.add_handler(CommandHandler("myscore", myscore))
    application.add_handler(CommandHandler("mystats", mystats))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("botstats", bot_stats))
    application.add_handler(CommandHandler("setcomp", set_group_compliment))
    application.add_handler(CommandHandler("comp_toggle", toggle_compliments))
    application.add_handler(CommandHandler("groupleaderboard", groupleaderboard))
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CommandHandler("removeadmin", remove_admin))
    application.add_handler(CommandHandler("adminlist", adminlist))
    application.add_handler(CommandHandler("addquestion", addquestion))
    application.add_handler(CommandHandler("questions", questions_stats))
    application.add_handler(CommandHandler("addcompliment", addcompliment))
    application.add_handler(CommandHandler("listcompliments", listcompliments))
    application.add_handler(CommandHandler("delcompliment", delcompliment))
    application.add_handler(CommandHandler("footer", footer_cmd))
    application.add_handler(CommandHandler("autoquiz", autoquiz))
    application.add_handler(CommandHandler("delallquestions", del_all_questions))
    application.add_handler(CommandHandler("delallcompliments", delallcompliments))
    application.add_handler(CommandHandler("scorecard", scorecard))

	# Add this among your other CallbackQueryHandlers
    application.add_handler(CallbackQueryHandler(verify_sub_callback, pattern="^verify_sub$"))
    # Inside main()
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CallbackQueryHandler(broadcast_callback, pattern="^bc_"))
    # Special Handlers
    application.add_handler(MessageHandler(filters.Document.ALL & ~filters.Chat(SOURCE_GROUP_ID), addquestion))
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    # --- JOB QUEUE SETUP ---
    jq = application.job_queue

    # Auto-quiz interval
    try:
        with db.get_db() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='autoquiz_interval'").fetchone()
            interval_min = int(row[0]) if row else 30
    except Exception:
        interval_min = 30 

    jq.run_repeating(auto_quiz_job, interval=interval_min * 60, first=20)

    # Nightly Leaderboard scheduled for 9:30 PM (21:30) IST
    # Because we set the default tzinfo above, we use a simple time(21, 30)
    jq.run_daily(
        nightly_leaderboard_job,
        time=time(hour=22, minute=0), 
        name="nightly_leaderboard",
        job_kwargs={
            'misfire_grace_time': 600, # 10 minute grace period
            'coalesce': True           
        }
    )

    print("🚀 NEETIQBot is fully secured and Online!")
    application.run_polling(drop_pending_updates=True)
	
