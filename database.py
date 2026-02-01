import os
import libsql_client
from contextlib import contextmanager
from datetime import datetime

# --- TURSO CONFIGURATION ---
# This pulls the values directly from Render Environment Variables
TURSO_URL = os.environ.get("TURSO_URL")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN")

# This check will prevent the crash and tell you exactly what is missing
if not TURSO_URL or not TURSO_TOKEN:
    raise ValueError("❌ DATABASE ERROR: TURSO_URL or TURSO_TOKEN is not set in Render Environment Variables!")
    
BOT_TOKEN = os.environ.get("BOT_TOKEN")

from contextlib import contextmanager
from datetime import datetime

# --- TURSO COMPATIBILITY LAYER ---
class RowWrapper:
    """Allows accessing Turso rows by column name, mimicking sqlite3.Row."""
    def __init__(self, row, columns):
        self.row = row
        self.columns = columns
    def __getitem__(self, key):
        if isinstance(key, str):
            return self.row[self.columns.index(key)]
        return self.row[key]
    def __iter__(self):
        return iter(self.row)

class TursoCursor:
    """Wrapper to make Turso client behave like a standard cursor."""
    def __init__(self, client):
        self.client = client
    def execute(self, sql, params=()):
        res = self.client.execute(sql, params)
        self.rows = [RowWrapper(r, res.columns) for r in res.rows]
        return self
    def executemany(self, sql, params_list):
        for params in params_list:
            self.client.execute(sql, params)
        return self
    def fetchone(self):
        return self.rows[0] if hasattr(self, 'rows') and self.rows else None
    def fetchall(self):
        return self.rows if hasattr(self, 'rows') else []
    def commit(self):
        pass # Turso handles auto-commit per execute call

@contextmanager
def get_db():
    """Synchronous context manager for Turso Cloud connection."""
    client = libsql_client.create_client_sync(url=TURSO_URL, auth_token=TURSO_TOKEN)
    try:
        yield TursoCursor(client)
    finally:
        client.close()

def init_db():
    """Initializes tables on Turso Cloud with Daily Stats and Streak tracking."""
    with get_db() as conn:
        # 1. Questions Bank
        conn.execute("""CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT, a TEXT, b TEXT, c TEXT, d TEXT, 
            correct TEXT, explanation TEXT)""")

        # 2. Poll Tracking
        conn.execute("""CREATE TABLE IF NOT EXISTS active_polls (
            poll_id TEXT PRIMARY KEY, 
            chat_id INTEGER, 
            correct_option_id INTEGER)""")

        # 3. User & Group Registration
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            username TEXT, first_name TEXT, joined_at TEXT)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY, type TEXT, title TEXT, added_at TEXT)""")

        conn.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_at TEXT)")

        # 4. Global Stats & Streak (Added last_activity_date)
        conn.execute("""CREATE TABLE IF NOT EXISTS stats (
            user_id INTEGER PRIMARY KEY, 
            attempted INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0, 
            score INTEGER DEFAULT 0, 
            current_streak INTEGER DEFAULT 0, 
            max_streak INTEGER DEFAULT 0, 
            last_activity_date TEXT)""")

        # 5. NEW: Daily Stats Table (Tracks unique stats per day)
        conn.execute("""CREATE TABLE IF NOT EXISTS daily_stats (
            user_id INTEGER, 
            day TEXT, 
            attempted INTEGER DEFAULT 0, 
            correct INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, day))""")

        # 6. Group Stats
        conn.execute("""CREATE TABLE IF NOT EXISTS group_stats (
            chat_id INTEGER, user_id INTEGER, score INTEGER DEFAULT 0, 
            attempted INTEGER DEFAULT 0, correct INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id))""")

        # 7. Customization & Settings
        conn.execute("CREATE TABLE IF NOT EXISTS compliments (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, text TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS group_compliments (chat_id INTEGER, type TEXT, text TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS group_settings (chat_id INTEGER PRIMARY KEY, compliments_enabled INTEGER DEFAULT 1)")
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        
        defaults = [
            ('footer_text', 'NEETIQBot'),
            ('footer_enabled', '1'),
            ('autoquiz_enabled', '0'),
            ('autoquiz_interval', '30'),
            ('compliments_enabled', '1')
        ]
        conn.executemany("INSERT OR IGNORE INTO settings VALUES (?,?)", defaults)
        
    print("✅ Turso Cloud Database Initialized with Daily Stats support!")
        

def update_user_stats(user_id, chat_id, is_correct, username=None, first_name=None):
    """Updates global, daily, and group stats with streak-reset logic."""
    today = datetime.now().strftime('%Y-%m-%d')
    score_change = 4 if is_correct else -1
    correct_inc = 1 if is_correct else 0

    with get_db() as conn:
        # 1. Ensure user exists in the users table
        conn.execute("""
            INSERT INTO users (user_id, username, first_name) 
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                username = excluded.username, first_name = excluded.first_name
        """, (user_id, username, first_name))

        # 2. Update Global Stats & Streak Logic
        if is_correct:
            # If CORRECT: +1 to current streak, update max_streak if current > max
            conn.execute("""
                INSERT INTO stats (user_id, attempted, correct, score, current_streak, max_streak, last_activity_date) 
                VALUES (?, 1, 1, 4, 1, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET 
                    attempted = attempted + 1,
                    correct = correct + 1,
                    score = score + 4,
                    current_streak = current_streak + 1,
                    max_streak = CASE WHEN current_streak + 1 > max_streak THEN current_streak + 1 ELSE max_streak END,
                    last_activity_date = ?
            """, (user_id, today, today))
        else:
            # If WRONG: Reset current_streak to 0
            conn.execute("""
                INSERT INTO stats (user_id, attempted, correct, score, current_streak, last_activity_date) 
                VALUES (?, 1, 0, -1, 0, ?)
                ON CONFLICT(user_id) DO UPDATE SET 
                    attempted = attempted + 1,
                    score = score - 1,
                    current_streak = 0,
                    last_activity_date = ?
            """, (user_id, today, today))

        # 3. Update Daily Stats Table (Today's Progress)
        conn.execute("""
            INSERT INTO daily_stats (user_id, day, attempted, correct) 
            VALUES (?, ?, 1, ?)
            ON CONFLICT(user_id, day) DO UPDATE SET 
                attempted = attempted + 1,
                correct = correct + ?
        """, (user_id, today, correct_inc, correct_inc))

        # 4. Update Group Stats (if applicable)
        if chat_id:
            conn.execute("""
                INSERT INTO group_stats (user_id, chat_id, attempted, correct, score) 
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET 
                    attempted = attempted + 1,
                    correct = correct + ?,
                    score = score + ?
            """, (user_id, chat_id, correct_inc, score_change, correct_inc, score_change))


def get_leaderboard_data(chat_id=None, limit=25):
    with get_db() as conn:
        name_sql = """
            COALESCE(
                CASE WHEN u.username IS NOT NULL AND u.username != '' THEN '@' || u.username ELSE NULL END,
                u.first_name,
                'Participant ' || stats_table.user_id
            ) AS display_name
        """
        if chat_id:
            query = f"SELECT {name_sql.replace('stats_table', 'gs')}, gs.attempted, gs.correct, gs.score FROM group_stats gs LEFT JOIN users u ON gs.user_id = u.user_id WHERE gs.chat_id = ? ORDER BY gs.score DESC LIMIT ?"
            return conn.execute(query, (chat_id, limit)).fetchall()
        else:
            query = f"SELECT {name_sql.replace('stats_table', 's')}, s.attempted, s.correct, s.score FROM stats s LEFT JOIN users u ON s.user_id = u.user_id ORDER BY s.score DESC LIMIT ?"
            return conn.execute(query, (limit,)).fetchall()

def delete_all_compliments():
    with get_db() as conn:
        conn.execute("DELETE FROM compliments")

def delete_all_questions():
    with get_db() as conn:
        conn.execute("DELETE FROM questions")

if __name__ == "__main__":
    init_db()

