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

# --- DATABASE LOGIC ---

def init_db():
    """Initializes tables on Turso Cloud."""
    with get_db() as conn:
        # Questions Bank
        conn.execute("""CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT, a TEXT, b TEXT, c TEXT, d TEXT, 
            correct TEXT, explanation TEXT)""")

        # Poll Tracking
        conn.execute("""CREATE TABLE IF NOT EXISTS active_polls (
            poll_id TEXT PRIMARY KEY, 
            chat_id INTEGER, 
            correct_option_id INTEGER)""")

        # User & Group Registration
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            username TEXT, first_name TEXT, joined_at TEXT)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY, type TEXT, title TEXT, added_at TEXT)""")

        conn.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_at TEXT)")

        # Stats & Scoring
        conn.execute("""CREATE TABLE IF NOT EXISTS stats (
            user_id INTEGER PRIMARY KEY, attempted INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0, score INTEGER DEFAULT 0, 
            current_streak INTEGER DEFAULT 0, max_streak INTEGER DEFAULT 0, last_date TEXT)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS group_stats (
            chat_id INTEGER, user_id INTEGER, score INTEGER DEFAULT 0, 
            attempted INTEGER DEFAULT 0, correct INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id))""")

        # Customization
        conn.execute("CREATE TABLE IF NOT EXISTS compliments (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, text TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS group_compliments (chat_id INTEGER, type TEXT, text TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS group_settings (chat_id INTEGER PRIMARY KEY, compliments_enabled INTEGER DEFAULT 1)")

        # Global Settings
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        
        defaults = [
            ('footer_text', 'NEETIQBot'),
            ('footer_enabled', '1'),
            ('autoquiz_enabled', '0'),
            ('autoquiz_interval', '30'),
            ('compliments_enabled', '1')
        ]
        conn.executemany("INSERT OR IGNORE INTO settings VALUES (?,?)", defaults)
        
    print("✅ Turso Cloud Database Initialized!")

def update_user_stats(user_id, chat_id, is_correct, username=None, first_name=None):
    with get_db() as conn:
        # 1. Update user identity
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, joined_at) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                username = excluded.username, 
                first_name = excluded.first_name
        """, (user_id, username, first_name, datetime.now().isoformat()))

        score_change = 4 if is_correct else -1
        correct_inc = 1 if is_correct else 0
        
        # Streak Logic: Increment if correct, reset to 0 if wrong
        new_streak_val = 1 if is_correct else 0

        # 2. Update Global Stats (including streak logic and negative score support)
        conn.execute(f"""
            INSERT INTO stats (user_id, attempted, correct, score, current_streak, max_streak, last_date) 
            VALUES (?, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                attempted = attempted + 1,
                correct = correct + ?,
                score = score + ?,
                max_streak = CASE 
                    WHEN {1 if is_correct else 0} = 1 THEN MAX(max_streak, current_streak + 1) 
                    ELSE max_streak 
                END,
                current_streak = CASE 
                    WHEN {1 if is_correct else 0} = 1 THEN current_streak + 1 
                    ELSE 0 
                END,
                last_date = ?
        """, (user_id, correct_inc, score_change, new_streak_val, new_streak_val, datetime.now().isoformat(),
              correct_inc, score_change, datetime.now().isoformat()))

        # 3. Update Group Stats
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
        # Improved name logic to handle missing users gracefully
        name_sql = """
            COALESCE(
                CASE WHEN u.username IS NOT NULL AND u.username != '' THEN '@' || u.username ELSE NULL END,
                u.first_name,
                'Participant ' || stats_table.user_id
            ) AS display_name
        """
        
        if chat_id:
            # Pulls group scores but joins with global stats to show the user's Max Streak
            query = f"""
                SELECT 
                    {name_sql.replace('stats_table', 'gs')}, 
                    gs.attempted, gs.correct, gs.score,
                    s.current_streak, s.max_streak
                FROM group_stats gs 
                LEFT JOIN users u ON gs.user_id = u.user_id 
                LEFT JOIN stats s ON gs.user_id = s.user_id
                WHERE gs.chat_id = ? 
                ORDER BY gs.score DESC 
                LIMIT ?
            """
            return conn.execute(query, (chat_id, limit)).fetchall()
        else:
            # Global leaderboard showing all stats including streaks
            query = f"""
                SELECT 
                    {name_sql.replace('stats_table', 's')}, 
                    s.attempted, s.correct, s.score, 
                    s.current_streak, s.max_streak 
                FROM stats s 
                LEFT JOIN users u ON s.user_id = u.user_id 
                ORDER BY s.score DESC 
                LIMIT ?
            """
            return conn.execute(query, (limit,)).fetchall()
            

def delete_all_compliments():
    with get_db() as conn:
        conn.execute("DELETE FROM compliments")

def delete_all_questions():
    with get_db() as conn:
        conn.execute("DELETE FROM questions")

if __name__ == "__main__":
    init_db()

