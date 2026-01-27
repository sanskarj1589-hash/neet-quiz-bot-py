import os
import libsql_client
from contextlib import contextmanager

# On Render, we will store these in 'Environment Variables'
TURSO_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

@contextmanager
def get_db():
    # This connects to your Turso cloud database
    conn = libsql_client.connect(TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
    try:
        yield conn
        # Note: libsql-client handles commits automatically in many cases
    finally:
        conn.close()
        

def init_db():
    with get_db() as conn:
        # --- 1. CORE SYSTEM TABLES ---
        # Questions Bank
        conn.execute("""CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT, a TEXT, b TEXT, c TEXT, d TEXT, 
            correct TEXT, explanation TEXT)""")

        # Poll Tracking (Crucial for scoring)
        conn.execute("""CREATE TABLE IF NOT EXISTS active_polls (
            poll_id TEXT PRIMARY KEY, 
            chat_id INTEGER, 
            correct_option_id INTEGER)""")

        # Sent Questions (If you still use tracking)
        conn.execute("""CREATE TABLE IF NOT EXISTS sent_questions (
            chat_id INTEGER, 
            q_id INTEGER, 
            PRIMARY KEY(chat_id, q_id))""")

        # --- 2. USER & GROUP REGISTRATION ---
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            username TEXT, 
            first_name TEXT, 
            joined_at TEXT)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY, 
            type TEXT, 
            title TEXT, 
            added_at TEXT)""")

        conn.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_at TEXT)")

        # --- 3. STATS & SCORING ---
        # Global Stats
        conn.execute("""CREATE TABLE IF NOT EXISTS stats (
            user_id INTEGER PRIMARY KEY, 
            attempted INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0, 
            score INTEGER DEFAULT 0, 
            current_streak INTEGER DEFAULT 0, 
            max_streak INTEGER DEFAULT 0, 
            last_date TEXT)""")

        # Group Specific Stats
        conn.execute("""CREATE TABLE IF NOT EXISTS group_stats (
            chat_id INTEGER, 
            user_id INTEGER, 
            score INTEGER DEFAULT 0, 
            attempted INTEGER DEFAULT 0, 
            correct INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id))""")

        # --- 4. COMPLIMENTS & GROUP CUSTOMIZATION ---
        # Global Compliments (Default)
        conn.execute("""CREATE TABLE IF NOT EXISTS compliments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            type TEXT, 
            text TEXT)""")

        # Group-Specific Custom Compliments (/setcomp)
        conn.execute("""CREATE TABLE IF NOT EXISTS group_compliments (
            chat_id INTEGER, 
            type TEXT, 
            text TEXT)""")

        # Group Settings (/comp_toggle)
        conn.execute("""CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY, 
            compliments_enabled INTEGER DEFAULT 1)""")

        # --- 5. GLOBAL BOT SETTINGS ---
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        
        defaults = [
            ('footer_text', 'NEETIQBot'),
            ('footer_enabled', '1'),
            ('autoquiz_enabled', '0'),
            ('autoquiz_interval', '30'),
            ('compliments_enabled', '1') # Global Master Switch
        ]
        conn.executemany("INSERT OR IGNORE INTO settings VALUES (?,?)", defaults)
        
        conn.commit()

def update_user_stats(user_id, chat_id, is_correct, username=None, first_name=None):
    today = str(date.today())
    with get_db() as conn:
        # --- IMPROVED: Sync User Info ---
        # We check for EITHER first_name or username to ensure we don't skip anyone
        if first_name or username:
            conn.execute("""
                INSERT OR REPLACE INTO users (user_id, username, first_name, joined_at) 
                VALUES (?, ?, ?, COALESCE((SELECT joined_at FROM users WHERE user_id=?), ?))
            """, (user_id, username, first_name, user_id, today))

        # --- Stats Logic ---
        conn.execute("INSERT OR IGNORE INTO stats (user_id) VALUES (?)", (user_id,))
        s = conn.execute("SELECT * FROM stats WHERE user_id=?", (user_id,)).fetchone()
        
        points = 4 if is_correct else -1
        new_streak = s['current_streak'] + 1 if is_correct else 0
        new_max = max(s['max_streak'], new_streak)

        conn.execute("""UPDATE stats SET attempted=attempted+1, correct=correct+?, 
                     score=score+?, current_streak=?, max_streak=?, last_date=?
                     WHERE user_id=?""", (1 if is_correct else 0, points, new_streak, new_max, today, user_id))
        
        if chat_id < 0:
            conn.execute("INSERT OR IGNORE INTO group_stats (chat_id, user_id) VALUES (?,?)", (chat_id, user_id))
            conn.execute("""UPDATE group_stats SET score=score+?, attempted=attempted+1, 
                         correct=correct+? WHERE chat_id=? AND user_id=?""",
                         (points, 1 if is_correct else 0, chat_id, user_id))


def get_compliment(c_type):
    with get_db() as conn:
        status = conn.execute("SELECT value FROM settings WHERE key='compliments_enabled'").fetchone()[0]
        if status == '0': return None
        res = conn.execute("SELECT text FROM compliments WHERE type=? ORDER BY RANDOM() LIMIT 1", (c_type,)).fetchone()
        return res[0] if res else None

def get_leaderboard_data(chat_id=None, limit=25):
    with get_db() as conn:
        # Priority: @username -> first_name -> fallback text
        # Using NULLIF to ensure empty strings aren't used
        name_logic = """
            COALESCE(
                CASE WHEN u.username IS NOT NULL AND u.username != '' THEN '@' || u.username ELSE NULL END,
                u.first_name,
                'Participant'
            )
        """
        
        if chat_id:
            query = f"""
                SELECT {name_logic}, gs.attempted, gs.correct, gs.score
                FROM group_stats gs 
                LEFT JOIN users u ON gs.user_id = u.user_id
                WHERE gs.chat_id = ? 
                ORDER BY gs.score DESC LIMIT ?"""
            return conn.execute(query, (chat_id, limit)).fetchall()
        
        query = f"""
            SELECT {name_logic}, s.attempted, s.correct, s.score
            FROM stats s 
            LEFT JOIN users u ON s.user_id = u.user_id
            ORDER BY s.score DESC LIMIT ?"""
        return conn.execute(query, (limit,)).fetchall()



if __name__ == "__main__":
    init_db()
    print("✅ Database Master Layer Ready.")

