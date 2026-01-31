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

# Channel IDs (Ensure Bot is Admin in both)
CHANNELS = {
    "@NEETIQBOTUPDATES": -1002973969945, # Replace with actual numeric ID
    "@SANSKAR279": -1002976165717      # Replace with actual numeric ID
}
SUPPORT_URL = "https://t.me/NEETIQsupportbot"


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
		
# ---------------- REGISTRATION ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    # 1. Registration Logic (Same as before)
    with db.get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at, status) VALUES (?,?,?,?,?)",
            (user.id, user.username, user.first_name, datetime.now().isoformat(), 'active')
        )

    # 2. Force Join Check (Private Only)
    if chat.type == 'private':
        not_joined = []
        for name, channel_id in CHANNELS.items():
            try:
                member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user.id)
                if member.status in ['left', 'kicked', 'restricted']:
                    not_joined.append(name)
            except Exception:
                continue # Skip if bot can't check

        if not_joined:
            buttons = [[InlineKeyboardButton(f"📢 Join {name}", url=f"https://t.me/{name.replace('@','')}")] for name in not_joined]
            buttons.append([InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{context.bot.username}?start=start")])
            
            return await update.message.reply_text(
                "⚠️ <b>Access Denied!</b>\n\nYou must join our update channels to use this bot.",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode="HTML"
            )

        # Handle Deep Linking for Scorecard
        if context.args and context.args[0] == "scorecard":
            return await scorecard(update, context)

        # Regular Welcome
        safe_name = html.escape(user.first_name)
        welcome = f"👋 <b>Welcome back, {safe_name}!</b>\n\nYour NEET preparation starts here. Use the menu below to navigate."
        btn = [
            [InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
            [InlineKeyboardButton("🛠️ Contact Support", url=SUPPORT_URL)]
        ]
        await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(btn), parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 <b>NEETIQBot Help Manual</b>\n\n"
        "👋 <b>Basics</b>\n"
        "• /start - Restart bot\n"
        "• /help - Show this menu\n\n"
        "📘 <b>Your Profile</b>\n"
        "• /mystats - Global stats\n"
        "• /scorecard - Subject breakdown (DM)\n\n"
        "🏆 <b>Rankings</b>\n"
        "• /leaderboard - Global Top 25\n"
        "• /top - Group daily leaderboard\n\n"
        "<i>Need more help? Click the button below to message our support bot.</i>"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Support Bot", url=SUPPORT_URL)],
        [InlineKeyboardButton("📢 Updates Channel", url="https://t.me/NEETIQBOTUPDATES")]
    ])
    
    await update.message.reply_text(help_text, reply_markup=keyboard, parse_mode="HTML")



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
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user  
    
    if not user: return
        
    user_id = user.id
    username = user.username
    first_name = user.first_name

    with db.get_db() as conn:
        # 1. Register/Sync User
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, joined_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                status = 'active'
        """, (user_id, username, first_name, datetime.now().isoformat()))
        
        # 2. Fetch Poll Data AND Subject
        # We now join with the 'questions' table to get the subject tag
        poll_data = conn.execute("""
            SELECT q.chat_id, q.correct_option_id, q.subject 
            FROM questions q 
            WHERE q.poll_id = ?
        """, (poll_id,)).fetchone()

    if not poll_data:
        return

    chat_id = poll_data[0]
    correct_option = poll_data[1]
    subject = poll_data[2] # This is 'Bio', 'Phy', or 'Che'
    
    is_correct = (len(answer.option_ids) > 0 and answer.option_ids[0] == correct_option)

    # 3. Update Subject-Aware Stats
    # We pass 'subject' to our new database function
    db.update_user_stats(user_id, is_correct, subject=subject)
    db.update_group_stats(user_id, chat_id, is_correct)

    # 4. Compliment Logic (Remains similar but cleaned up)
    await send_compliment(context, chat_id, is_correct, first_name, username, user_id)

async def send_compliment(context, chat_id, is_correct, first_name, username, user_id):
    """Helper to keep handle_poll_answer clean"""
    if chat_id > 0: return # Don't send compliments in DMs

    with db.get_db() as conn:
        # Check if compliments are enabled for this group
        setting = conn.execute("SELECT value FROM settings WHERE key = ?", (f"compliments_{chat_id}",)).fetchone()
        if setting and setting[0] == 'off': return

        c_type = "correct" if is_correct else "wrong"
        comp = conn.execute("SELECT text FROM compliments WHERE type = ? ORDER BY RANDOM() LIMIT 1", (c_type,)).fetchone()

    if comp:
        compliment_text = comp[0]
        safe_name = html.escape(first_name)
        mention = f"@{html.escape(username)}" if username else f'<a href="tg://user?id={user_id}">{safe_name}</a>'
        final_text = compliment_text.replace("{user}", mention)

        try:
            await context.bot.send_message(chat_id=chat_id, text=final_text, parse_mode="HTML")
        except: pass


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
        # Fetching stats from your existing 'stats' table
        s = conn.execute("SELECT user_id, attempted, correct, score, current_streak, max_streak FROM stats WHERE user_id = ?", (user.id,)).fetchone()
        
        if not s:
            return await update.message.reply_text("❌ <b>No statistics found!</b>\nAnswer some quizzes to generate your profile.", parse_mode="HTML")

        # Column mapping: (user_id:0, attempted:1, correct:2, score:3, current_streak:4, max_streak:5)
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
            gr_row = conn.execute("SELECT COUNT(*) + 1 FROM group_stats WHERE chat_id = ? AND score > ?",
                                 (chat_id, score)).fetchone()
            group_rank = gr_row[0] if gr_row else "N/A"

    # 1. Performance Logic (NEET Scoring: +4, -1)
    accuracy = (correct / attempted * 100) if attempted > 0 else 0
    wrong = attempted - correct
    xp = (correct * 4) - (wrong * 1)
    xp = max(0, xp)  # XP cannot be negative

    # 2. Dynamic Rank Titles (Keeping your specific titles)
    if xp > 1000: rank_title = "🏥 AIIMS Dean"
    elif xp > 500: rank_title = "👨‍⚕️ Senior Consultant"
    elif xp > 300: rank_title = "💉 Resident Doctor"
    elif xp > 150: rank_title = "🩺 Gold Intern"
    elif xp > 50:  rank_title = "📚 Elite Aspirant"
    else:          rank_title = "🧬 Medical Student"

    # 3. HTML Profile Construction (Standardized Box Format)
    safe_name = html.escape(user.first_name)
    divider = "<b>━━━━━━━━━━━━━━━━━━━━</b>"

    text = (
        f"🪪 <b>NEETIQ USER PROFILE</b>\n"
        f"{divider}\n"
        f"👤 <b>NAME :</b> <code>{safe_name}</code>\n"
        f"🏅 <b>RANK :</b> <b>{rank_title}</b>\n"
        f"{divider}\n"
        f"📊 <b>POSITION & PROGRESS</b>\n"
        f"<code>╭────────────────────</code>\n"
        f"<code>│ 🏆 Global  : #{global_rank}</code>\n"
        f"<code>│ 👥 Group   : #{group_rank}</code>\n"
        f"<code>│ 🧬 Total XP: {xp:,}</code>\n"
        f"<code>╰────────────────────</code>\n\n"
        f"📈 <b>ACCURACY TRACKER</b>\n"
        f"<code>╭────────────────────</code>\n"
        f"<code>│ 📝 Attempted : {attempted}</code>\n"
        f"<code>│ ✅ Correct   : {correct}</code>\n"
        f"<code>│ 🎯 Accuracy  : {accuracy:.1f}%</code>\n"
        f"<code>╰────────────────────</code>\n\n"
        f"🔥 <b>STREAK MONITOR</b>\n"
        f"<code>╭────────────────────</code>\n"
        f"<code>│ ⚡ Current : {c_streak}</code>\n"
        f"<code>│ 💎 Best    : {m_streak}</code>\n"
        f"<code>╰────────────────────</code>\n"
        f"{divider}\n"
        f"NEETIQbot"
    )

    await update.message.reply_text(
        text, 
        parse_mode="HTML",
        disable_web_page_preview=True
	)


async def scorecard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    # 1. Restriction: Private Chat Only
    if chat.type != 'private':
        # Send a button to redirect them to DM
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🪪 View My Detailed Scorecard", url=f"https://t.me/{context.bot.username}?start=scorecard")]
        ])
        return await update.message.reply_text(
            "❌ <b>Detailed Scorecards are private.</b>\nClick the button below to check your subject-wise performance!",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    with db.get_db() as conn:
        # Fetch detailed subject stats
        # Indices: user_id:0, score:1, bio_att:2, bio_cor:3, phy_att:4, phy_cor:5, che_att:6, che_cor:7
        # Note: Adjust column names if they differ in your Turso table
        s = conn.execute("""
            SELECT user_id, score, bio_att, bio_cor, phy_att, phy_cor, che_att, che_cor, 
            current_streak, max_streak FROM stats WHERE user_id = ?
        """, (user.id,)).fetchone()
        
        if not s:
            return await update.message.reply_text("❌ <b>No data found!</b>\nSolve subject-wise quizzes to see your scorecard.", parse_mode="HTML")

        # Map variables
        score = s[1]
        bio_att, bio_cor = s[2], s[3]
        phy_att, phy_cor = s[4], s[5]
        che_att, che_cor = s[6], s[7]
        c_streak, m_streak = s[8], s[9]

        # Global Rank
        g_rank_row = conn.execute("SELECT COUNT(*) + 1 FROM stats WHERE score > ?", (score,)).fetchone()
        global_rank = g_rank_row[0]

    # 2. Accuracy Helper
    def calc_acc(cor, att):
        return (cor / att * 100) if att > 0 else 0

    # 3. Dynamic Rank Title (Same as mystats for consistency)
    if score > 1000: rank_title = "🏥 AIIMS Dean"
    elif score > 500: rank_title = "👨‍⚕️ Senior Consultant"
    elif score > 300: rank_title = "💉 Resident Doctor"
    elif score > 150: rank_title = "🩺 Gold Intern"
    elif score > 50:  rank_title = "📚 Elite Aspirant"
    else:          rank_title = "🧬 Medical Student"

    # 4. HTML Construction
    safe_name = html.escape(user.first_name)
    divider = "<b>━━━━━━━━━━━━━━━━━━━━</b>"

    text = (
        f"🪪 <b>NEETIQ USER SCORECARD</b>\n"
        f"{divider}\n"
        f"👤 <b>NAME :</b> <code>{safe_name}</code>\n"
        f"🏅 <b>RANK :</b> <b>{rank_title}</b>\n"
        f"{divider}\n"
        f"📊 <b>POSITION & PROGRESS</b>\n"
        f"<code>╭────────────────────</code>\n"
        f"<code>│ 🏆 Global  : #{global_rank}</code>\n"
        f"<code>│ 🧬 Total XP: {score:,}</code>\n"
        f"<code>╰────────────────────</code>\n\n"
        f"📊 <b>SUBJECT PERFORMANCE</b>\n"
        f"<code>╭────────────────────</code>\n"
        f"<code>│ 🧬 BIO : {bio_cor}/{bio_att}</code>\n"
        f"<code>│ ⚡ PHY : {phy_cor}/{phy_att}</code>\n"
        f"<code>│ 🧪 CHE : {che_cor}/{che_att}</code>\n"
        f"<code>╰────────────────────</code>\n\n"
        f"📈 <b>ACCURACY TRACKER</b>\n"
        f"<code>╭────────────────────</code>\n"
        f"<code>│ 🧬 BIO Acc : {calc_acc(bio_cor, bio_att):.1f}%</code>\n"
        f"<code>│ ⚡ PHY Acc : {calc_acc(phy_cor, phy_att):.1f}%</code>\n"
        f"<code>│ 🧪 CHE Acc : {calc_acc(che_cor, che_att):.1f}%</code>\n"
        f"<code>╰────────────────────</code>\n\n"
        f"🔥 <b>STREAK MONITOR</b>\n"
        f"<code>╭────────────────────</code>\n"
        f"<code>│ ⚡ Current : {c_streak}</code>\n"
        f"<code>│ 💎 Best    : {m_streak}</code>\n"
        f"<code>╰────────────────────</code>\n"
        f"{divider}\n"
        f"NEETIQbot"
    )

    await update.message.reply_text(text, parse_mode="HTML")



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
async def add_subject_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Modified version to handle Bio, Phy, and Che subjects separately."""
    if not await is_admin(update.effective_user.id): return
    
    # 1. Determine Subject from the command used
    cmd = update.effective_message.text.split()[0].lower() if update.effective_message.text else ""
    if "bio" in cmd: subject = "Bio"
    elif "phy" in cmd: subject = "Phy"
    elif "che" in cmd: subject = "Che"
    else: subject = "General"

    content = ""
    # Handle .txt file upload
    if update.message.document and update.message.document.file_name.endswith('.txt'):
        file = await context.bot.get_file(update.message.document.file_id)
        content = (await file.download_as_bytearray()).decode('utf-8')
    # Handle direct text
    elif update.message.text:
        # Remove the command (e.g., /addbioquestions) from the text
        content = update.message.text.split(maxsplit=1)[1] if len(update.message.text.split()) > 1 else ""

    if not content:
        return await update.message.reply_text(f"❌ Please provide text or a .txt file for {subject}.")

    # Split by double newlines to separate different questions
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
                    # Join remaining lines to keep question formatting (e.g., equations or lists)
                    q_text = "\n".join(lines[:-6]) 

                    if correct not in ['1', '2', '3', '4', 'A', 'B', 'C', 'D']:
                        skipped_count += 1
                        continue

                    # UPDATED: Added 'subject' column to the insertion
                    conn.execute(
                        "INSERT INTO questions (question, a, b, c, d, correct, explanation, subject) VALUES (?,?,?,?,?,?,?,?)",
                        (q_text, opt_a, opt_b, opt_c, opt_d, correct, explanation, subject)
                    )
                    added_count += 1
                except Exception:
                    skipped_count += 1
            else:
                skipped_count += 1

    await update.message.reply_text(
        apply_footer(f"📊 *{subject} Import Summary:*\n✅ Added: `{added_count}`\n⚠️ Skipped: `{skipped_count}`")
					)
	
async def questions_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays remaining questions breakdown by subject."""
    if not await is_admin(update.effective_user.id): return
    
    with db.get_db() as conn:
        # Fetching counts for each category
        total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        bio = conn.execute("SELECT COUNT(*) FROM questions WHERE subject = 'Bio'").fetchone()[0]
        phy = conn.execute("SELECT COUNT(*) FROM questions WHERE subject = 'Phy'").fetchone()[0]
        che = conn.execute("SELECT COUNT(*) FROM questions WHERE subject = 'Che'").fetchone()[0]

    # Matching your requested format
    response = (
        "📊 *Remaining questions*\n"
        f"🔹 *Total:* `{total}`\n\n"
        f"🧬 *Biology:* `{bio}`\n"
        f"⚡ *Physics:* `{phy}`\n"
        f"🧪 *Chemistry:* `{che}`"
    )
    
    await update.message.reply_text(response, parse_mode="Markdown")
	

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


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initializes broadcast with targeting buttons."""
    if not await is_admin(update.effective_user.id): return

    # Check if admin is replying to a message or provided text
    if not update.message.reply_to_message and not context.args:
        return await update.message.reply_text(
            "❌ <b>Usage:</b> Reply to a formatted message with <code>/broadcast</code> "
            "or type <code>/broadcast &lt;text&gt;</code>", parse_mode="HTML"
        )

    # Store the content to be broadcasted in context for the next step
    context.user_data['broadcast_msg'] = update.message.reply_to_message if update.message.reply_to_message else update.message
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Users", callback_data="bc_users"),
         InlineKeyboardButton("👥 Groups", callback_data="bc_groups")],
        [InlineKeyboardButton("🌎 Both", callback_data="bc_all")],
        [InlineKeyboardButton("❌ Cancel", callback_data="bc_cancel")]
    ])

    await update.message.reply_text(
        "📢 <b>Broadcast Control</b>\nSelect target audience for this message:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def handle_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes the broadcast based on selected target."""
    query = update.callback_query
    await query.answer()
    
    target = query.data
    if target == "bc_cancel":
        return await query.edit_message_text("❌ Broadcast cancelled.")

    source_msg = context.user_data.get('broadcast_msg')
    if not source_msg:
        return await query.edit_message_text("❌ Error: Message content lost.")

    # Extract original HTML to preserve gap lines and bolding
    if query.data == "bc_users" or query.data == "bc_all":
        # Logic to fetch users/groups from DB remains same
        pass 

    await query.edit_message_text("⏳ <b>Broadcasting...</b>", parse_mode="HTML")

    # --- THE CORE SENDER LOGIC ---
    # We use source_msg.text_html or source_msg.caption_html to keep formatting
    raw_content = source_msg.text_html if source_msg.text else source_msg.caption_html
    # Remove the command itself from the text if it was typed
    raw_content = raw_content.replace("/broadcast", "").strip()

    divider = "<b>━━━━━━━━━━━━━━━━━━━━</b>"
    final_text = f"📢 <b>NEETIQ ANNOUNCEMENT</b>\n{divider}\n\n{raw_content}\n\n{divider}"

    # ... [Loop logic with asyncio.sleep(0.05) remains similar to your code] ...
    # IMPORTANT: Use 'await context.bot.send_message(..., text=final_text, parse_mode="HTML")'


			

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


# --- STARTUP HOOK ---
async def on_startup(application):
    """
    Initializes the database within the running event loop 
    to prevent 'RuntimeError: no running event loop'.
    """
    print("🔄 Initializing Database...")
    db.init_db()
    print("✅ Database Synchronization Complete.")

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
    # 1. Start the Keep-Alive Web Server (Background thread)
    print("🌐 Starting Keep-Alive server...")
    keep_alive()

    # 2. Define Timezone for Kolkata
    ist_timezone = pytz.timezone('Asia/Kolkata')

    # 3. Build Application
    # We use post_init to call db.init_db inside the async loop
    application = (
        ApplicationBuilder()
        .token(os.environ.get("BOT_TOKEN")) 
        .defaults(Defaults(parse_mode=ParseMode.HTML, tzinfo=ist_timezone)) 
        .post_init(on_startup)  # <--- CRITICAL FIX
        .build()
    )

    # --- HANDLERS ---
    
    # A. Mirroring Logic (Highest Priority)
    application.add_handler(MessageHandler(
        filters.Chat(SOURCE_GROUP_ID) & 
        (~filters.COMMAND) & 
        (filters.TEXT | filters.PHOTO | filters.Document.ALL | filters.POLL), 
        mirror_messages
    ))

    # B. User & Stats Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("randomquiz", send_random_quiz))
    application.add_handler(CommandHandler("myscore", myscore))
    application.add_handler(CommandHandler("mystats", mystats))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("groupleaderboard", groupleaderboard))
    application.add_handler(CommandHandler("scorecard", scorecard))

    # C. Admin Control Commands
    application.add_handler(CommandHandler("botstats", bot_stats))
    application.add_handler(CommandHandler("questions", questions_stats))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CommandHandler("removeadmin", remove_admin))
    application.add_handler(CommandHandler("adminlist", adminlist))
    application.add_handler(CommandHandler("footer", footer_cmd))
    
    # D. Subject-Specific Question Adding
    application.add_handler(CommandHandler("addquestion", add_subject_questions))
    application.add_handler(CommandHandler("addbioquestions", add_subject_questions))
    application.add_handler(CommandHandler("addphyquestions", add_subject_questions))
    application.add_handler(CommandHandler("addchequestions", add_subject_questions))

    # E. Content Management
    application.add_handler(CommandHandler("addcompliment", addcompliment))
    application.add_handler(CommandHandler("listcompliments", listcompliments))
    application.add_handler(CommandHandler("delcompliment", delcompliment))
    application.add_handler(CommandHandler("delallquestions", del_all_questions))
    application.add_handler(CommandHandler("delallcompliments", delallcompliments))

    # F. Group Settings
    application.add_handler(CommandHandler("setcomp", set_group_compliment))
    application.add_handler(CommandHandler("comp_toggle", toggle_compliments))
    application.add_handler(CommandHandler("autoquiz", autoquiz))

    # G. Special Handlers (Polls and Bulk Text Files)
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    application.add_handler(MessageHandler(
        filters.Document.ALL & ~filters.Chat(SOURCE_GROUP_ID), 
        add_subject_questions
    ))

    # --- JOB QUEUE SETUP ---
    jq = application.job_queue

    # Fetch Interval from Settings (We use a default here to avoid sync issues during first start)
    interval_min = 30 

    # Background Tasks
    jq.run_repeating(auto_quiz_job, interval=interval_min * 60, first=20)
    jq.run_daily(
        nightly_leaderboard_job,
        time=time(hour=21, minute=0), # 9:00 PM IST
        name="nightly_leaderboard",
        job_kwargs={'misfire_grace_time': 600, 'coalesce': True}
    )

    print("🚀 NEETIQBot is fully secured and Online!")
    application.run_polling(drop_pending_updates=True)
	
