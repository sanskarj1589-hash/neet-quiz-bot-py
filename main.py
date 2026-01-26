import logging
import asyncio                                                                     from datetime import datetime, time                                                from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,                                                                    ContextTypes,
    PollAnswerHandler,                                                                 MessageHandler,                                                                    filters,                                                                           Defaults
)                                                                                  import database as db                                                                                                                                                 # ---------------- CONFIG ----------------
# Replace with your actual Bot Token
BOT_TOKEN = "8203396114:AAE_Ii9RuLvhCA64PRPwq1BZVc7bEPZmq0g"                       OWNER_ID = 6435499094

# Logging setup                                                                    logging.basicConfig(                                                                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)                                                                                  logger = logging.getLogger(__name__)                                                                                                                                  # Professional Defaults (MarkdownV2 for cleaner text)
# Note: Using standard Markdown for simplicity to avoid escape errors              defaults = Defaults(parse_mode="Markdown")                                         
# ---------------- HELPERS ----------------                                        
def apply_footer(text: str) -> str:                                                    """Applies the professional divider and custom footer text."""
    with db.get_db() as conn:
        f_row = conn.execute("SELECT value FROM settings WHERE key='footer_text'").fetchone()
        f_en = conn.execute("SELECT value FROM settings WHERE key='footer_enabled'").fetchone()                                                                                                                                                              footer_text = f_row[0] if f_row else "NEETIQBot"
    enabled = f_en[0] if f_en else "1"
                                                                                       if enabled == '1':                                                                     return f"{text}\n\n━━━━━━━━━━━━━━━\n{footer_text}"
    return text

async def is_admin(user_id: int) -> bool:                                              """Check if a user has admin privileges or is the owner."""
    if user_id == OWNER_ID:                                                                return True
    with db.get_db() as conn:                                                              res = conn.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone()                                                                                     return res is not None
                                                                                   # ---------------- REGISTRATION ----------------
                                                                                   async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user                                                       chat = update.effective_chat

    with db.get_db() as conn:                                                              conn.execute(                                                                          "INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at) VALUES (?,?,?,?)",
            (user.id, user.username, user.first_name, str(datetime.now()))                 )
        if chat.type != 'private':
            conn.execute(
                "INSERT OR IGNORE INTO chats (chat_id, type, title, added_at) VALUES (?,?,?,?)",
                (chat.id, chat.type, chat.title, str(datetime.now()))
            )
                                                                                       if chat.type == 'private':
        welcome = (
            f"👋 *Welcome to NEETIQBot, {user.first_name}!*\n\n"                               "I am your dedicated NEET preparation assistant. "
            "I provide high-quality MCQs, track your streaks, and manage competitive leaderboards.\n\n"
            "📌 *Use* /help *to see all available commands.*"                              )
        btn = [[InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]]                                                      await update.message.reply_text(apply_footer(welcome), reply_markup=InlineKeyboardMarkup(btn))
    else:
        group_msg = f"🎉 *Group successfully registered with NEETIQBot!*\n\nPreparing {chat.title} for upcoming quizzes."                                                     await update.message.reply_text(apply_footer(group_msg))
                                                                                   async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (                                                                          "📖 *NEETIQBot Command List*\n\n"                                                  "👋 *Basic Commands*\n"
        "/start - Register and start the bot\n"
        "/help - Display this help manual\n\n"                                             "📘 *Quiz System*\n"
        "/randomquiz - Receive a random NEET MCQ\n"
        "/myscore - View your point summary\n"                                             "/mystats - Detailed performance analysis\n\n"                                     "🏆 *Leaderboards*\n"
        "/leaderboard - Global rankings (Top 25)\n"                                        "/groupleaderboard - Group specific rankings"
    )                                                                                  await update.message.reply_text(apply_footer(help_text))                       
# ---------------- QUIZ SYSTEM ----------------
                                                                                   async def send_random_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):        """Sends a random NEET MCQ and permanently deletes it from the DB to prevent repetition."""
    chat_id = update.effective_chat.id                                             
    with db.get_db() as conn:
        # 1. Fetch any random question currently in the database
        q = conn.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT 1").fetchone()

    if not q:
        # No need to reset sent_questions because we are deleting questions permanently
        return await update.message.reply_text(
            "📭 *Database Empty!* All questions have been used and deleted. "                  "Please upload new questions using /addquestion."                              )

    options = [q['a'], q['b'], q['c'], q['d']]                                     
    # Map correct answer (supports 1-4 or A-D)
    correct_map = {'1': 0, '2': 1, '3': 2, '4': 3, 'A': 0, 'B': 1, 'C': 2, 'D': 3}     c_idx = correct_map.get(str(q['correct']).upper(), 0)                          
    try:
        # 2. Send the Poll                                                                 msg = await context.bot.send_poll(                                                     chat_id=chat_id,
            question=f"🧠 *NEET MCQ:*\n\n{q['question']}",                                     options=options,
            type=Poll.QUIZ,                                                                    correct_option_id=c_idx,
            explanation=f"📖 *Explanation:*\n{q['explanation']}",                              is_anonymous=False
        )                                                                          
        # 3. Track poll for answers and IMMEDIATELY delete the question                    with db.get_db() as conn:
            # Save poll info so /myscore works                                                 conn.execute("INSERT INTO active_polls VALUES (?,?,?)", (msg.poll.id, chat_id, c_idx))                                                                    
            # Delete the question by ID so it can never be sent again                          conn.execute("DELETE FROM questions WHERE id = ?", (q['id'],))         
    except Exception as e:                                                                 logger.error(f"Error in Quiz Flow: {e}")
        await update.message.reply_text("❌ Failed to process the quiz. Please check database logs.")                                                                 

                                                                                   async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):      """Processes the user's answer and updates streaks/scores with group-specific compliments."""
    answer = update.poll_answer                                                        poll_id = answer.poll_id                                                           user_id = answer.user.id

    with db.get_db() as conn:                                                              poll_data = conn.execute("SELECT * FROM active_polls WHERE poll_id = ?", (poll_id,)).fetchone()

    if not poll_data:                                                                      return

    chat_id = poll_data['chat_id']
    correct_option = poll_data['correct_option_id']                                    is_correct = (answer.option_ids[0] == correct_option)                          
    # Update Global and Group Stats
    db.update_user_stats(user_id, chat_id, is_correct)                             
    # --- UPDATED COMPLIMENT SYSTEM WITH TOGGLE CHECK ---
    with db.get_db() as conn:
        # Check if this specific group has disabled compliments                            setting = conn.execute("SELECT compliments_enabled FROM group_settings WHERE chat_id = ?", (chat_id,)).fetchone()
        # Default to enabled (1) if no setting found                                       if setting and setting[0] == 0:                                                        return

    c_type = "correct" if is_correct else "wrong"                                  
    with db.get_db() as conn:
        # 1. Try to fetch a group-specific custom compliment (/setcomp)
        comp = conn.execute(                                                                   "SELECT text FROM group_compliments WHERE chat_id = ? AND type = ? ORDER BY RANDOM() LIMIT 1",
            (chat_id, c_type)                                                              ).fetchone()                                                               
        # 2. If not found, fallback to global compliments
        if not comp:                                                                           comp = conn.execute(
                "SELECT text FROM compliments WHERE type = ? ORDER BY RANDOM() LIMIT 1",
                (c_type,)                                                                      ).fetchone()

    if comp:
        compliment_text = comp[0]                                                          final_text = compliment_text.replace("{user}", f"*{answer.user.first_name}*")

        if chat_id < 0: # Send in groups                                                       try:
                await context.bot.send_message(
                    chat_id=chat_id,                                                                   text=final_text,                                                                   parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error sending compliment: {e}")                     

# ---------------- PERFORMANCE STATS ----------------                                                                                                                 async def myscore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a quick summary of the user's current score."""
    user = update.effective_user                                                       with db.get_db() as conn:                                                              s = conn.execute("SELECT * FROM stats WHERE user_id = ?", (user.id,)).fetchone()
                                                                                       if not s:                                                                              return await update.message.reply_text("❌ *No data found.* Participate in a quiz to generate stats!")
                                                                                       text = (                                                                               "📊 *Your Score Summary*\n\n"
        f"Total Attempted: `{s['attempted']}`\n"
        f"Correct Answers: `{s['correct']}`\n"                                             f"Incorrect Answers: `{s['attempted'] - s['correct']}`\n"                          f"Current Score: `{s['score']}`"
    )
    await update.message.reply_text(apply_footer(text))                                                                                                               async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a detailed performance analysis and rankings."""
    user = update.effective_user                                                       with db.get_db() as conn:
        s = conn.execute("SELECT * FROM stats WHERE user_id = ?", (user.id,)).fetchone()
                                                                                           # Calculate Global Rank
        rank_val = 0
        if s:                                                                                  rank_row = conn.execute("SELECT COUNT(*) + 1 FROM stats WHERE score > ?", (s['score'],)).fetchone()
            rank_val = rank_row[0]                                                 
        # Calculate Group Rank (if applicable)
        g_rank = "N/A"                                                                     if update.effective_chat.type != 'private' and s:
            gr = conn.execute("SELECT COUNT(*) + 1 FROM group_stats WHERE chat_id = ? AND score > ?",                                                                                               (update.effective_chat.id, s['score'])).fetchone()
            g_rank = f"#{gr[0]}"                                                   
    if not s:                                                                              return await update.message.reply_text("❌ *No statistics available yet!*")
                                                                                       accuracy = (s['correct'] / s['attempted'] * 100) if s['attempted'] > 0 else 0

    text = (                                                                               "📊 *Detailed Performance Stats*\n\n"                                              f"📘 Total Attempts: `{s['attempted']}`\n"                                         f"✅ Correct: `{s['correct']}`\n"
        f"❌ Wrong: `{s['attempted'] - s['correct']}`\n"                                   f"🎯 Accuracy: `{accuracy:.2f}%`\n"                                                f"🔥 Best Streak: `{s['max_streak']}`\n\n"                                         f"🌞 Current Streak: `{s['current_streak']}`\n"
        f"🏆 Lifetime Score: `{s['score']}`\n\n"
        f"🌍 Global Rank: `#{rank_val}`\n"                                                 f"👥 Group Rank: `{g_rank}`"
    )
    await update.message.reply_text(apply_footer(text))                                                                                                               # ---------------- LEADERBOARD LOGIC ----------------

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):             """Displays the Global Leaderboard (Top 25)."""                                    rows = db.get_leaderboard_data(limit=25)

    if not rows:
        return await update.message.reply_text("📭 The Global Leaderboard is currently empty.")
                                                                                       text = "🌍 *Global Leaderboard (Top 25)*\n\n"
    for i, r in enumerate(rows, 1):                                                        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🔹"
        text += f"{medal} *{r[0]}*\n📘 Att: `{r[1]}` | ✅ Cor: `{r[2]}` | 🏆 Score: `{r[3]}`\n\n"
                                                                                       await update.message.reply_text(apply_footer(text))
                                                                                   async def groupleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the Leaderboard specific to the current group."""                      if update.effective_chat.type == 'private':
        return await update.message.reply_text("❌ This command is only available within Groups.")
                                                                                       chat_id = update.effective_chat.id
    rows = db.get_leaderboard_data(chat_id=chat_id, limit=10)                      
    text = f"👥 *{update.effective_chat.title} Leaderboard*\n\n"                       if not rows:
        text += "No participants yet. Start a quiz to rank up!"
    else:                                                                                  for i, r in enumerate(rows, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            text += f"{medal} *{r[0]}*\n📘 Att: `{r[1]}` | ✅ Cor: `{r[2]}` | 🏆 Score: `{r[3]}`\n\n"
                                                                                       text += "🎉 Congratulations to all top performers!"
    await update.message.reply_text(apply_footer(text))                            
# ---------------- ADMIN MANAGEMENT ----------------                               
async def adminlist(update: Update, context: ContextTypes.DEFAULT_TYPE):               """Lists all authorized admins."""
    if not await is_admin(update.effective_user.id): return                            with db.get_db() as conn:
        admins = conn.execute("SELECT user_id FROM admins").fetchall()             
    text = "👮 *Authorized Admins:*\n\n"                                               text += f"• `{OWNER_ID}` (Owner)\n"
    for adm in admins:                                                                     if adm[0] != OWNER_ID:                                                                 text += f"• `{adm[0]}`\n"                                                  await update.message.reply_text(apply_footer(text))
                                                                                   async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return                                    try:
        new_id = int(context.args[0])                                                      with db.get_db() as conn:
            conn.execute("INSERT OR IGNORE INTO admins (user_id, added_at) VALUES (?,?)",
                         (new_id, str(datetime.now())))                                    await update.message.reply_text(f"✅ User `{new_id}` is now an Admin.")        except:                                                                                await update.message.reply_text("❌ Usage: `/addadmin <user_id>`")    
