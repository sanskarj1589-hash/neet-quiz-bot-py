import random
from contextlib import contextmanager
from datetime import datetime, date
import libsql_client as libsql

# --- TURSO CONFIGURATION ---
# Protocol set to https for Render compatibility
DB_URL = "https://neetiq-db-sanskarj1589-hash.aws-ap-south-1.turso.io"
# Your provided token
DB_TOKEN = "EyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3Njk1MTU0MTksImlkIjoiYmZkYjZlOGUtMGJmNS00Nzg3LThjNGYtOWQ4ODY2ZGY3Mjk1IiwicmlkIjoiZTY0MmQ1YjgtZTYwMy00ZjE3LWE4M2EtZjlkOTg4ODQ0N2Q3In0.6Hh3ioXIPetRRd_jHcfR8xWRV8mOVGNn_1FeyVJeJirk9UGajwMnJ5_Sn1pYAdsLR_hojZZPXEtXuPfaGGD_Bw"

class LibsqlWrapper:
    """Wrapper to make Libsql look like standard SQLite for main script compatibility"""
    def __init__(self, client):
        self.client = client
        self.last_result = None

    def execute(self, stmt, args=None):
        self.last_result = self.client.execute(stmt, args or [])
        return self

    def fetchone(self):
        if self.last_result and self.last_result.rows:
            return self.last_result.rows[0]
        return None

    def fetchall(self):
        if self.last_result:
            return self.last_result.rows
        return []

    def commit(self):
        pass

    def close(self):
        self.client.close()

@contextmanager
def get_db():
    client = libsql.create_client_sync(url=DB_URL, auth_token=DB_TOKEN)
    wrapper = LibsqlWrapper(client)
    try:
        yield wrapper
    finally:
        wrapper.close()

def init_db():
    with get_db() as conn:
        # --- CORE TABLES ---
        conn.execute("""CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT, a TEXT, b TEXT, c TEXT, d TEXT, 
            correct TEXT, explanation TEXT)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS active_polls (
            poll_id TEXT PRIMARY KEY, chat_id INTEGER, correct_option_id INTEGER)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS sent_questions (
            chat_id INTEGER, q_id INTEGER, PRIMARY KEY(chat_id, q_id))""")

        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, joined_at TEXT)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY, type TEXT, title TEXT, added_at TEXT)""")

        conn.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, added_at TEXT)")

        conn.execute("""CREATE TABLE IF NOT EXISTS stats (
            user_id INTEGER PRIMARY KEY, attempted INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0, score INTEGER DEFAULT 0, 
            current_streak INTEGER DEFAULT 0, max_streak INTEGER DEFAULT 0, last_date TEXT)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS group_stats (
            chat_id INTEGER, user_id INTEGER, score INTEGER DEFAULT 0, 
            attempted INTEGER DEFAULT 0, correct INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id))""")

        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        
        defaults = [
            ('footer_text', 'NEETIQBot'),
            ('footer_enabled', '1'),
            ('autoquiz_enabled', '0'),
            ('autoquiz_interval', '30'),
            ('compliments_enabled', '1')
        ]
        for key, val in defaults:
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

def update_user_stats(user_id, chat_id, is_correct, username=None, first_name=None):
    today = str(date.today())
    with get_db() as conn:
        if first_name or username:
            conn.execute("""
                INSERT OR REPLACE INTO users (user_id, username, first_name, joined_at) 
                VALUES (?, ?, ?, COALESCE((SELECT joined_at FROM users WHERE user_id=?), ?))
            """, (user_id, username, first_name, user_id, today))

        conn.execute("INSERT OR IGNORE INTO stats (user_id) VALUES (?)", (user_id,))
        s = conn.execute("SELECT attempted, correct, score, current_streak, max_streak FROM stats WHERE user_id=?", (user_id,)).fetchone()
        
        points = 4 if is_correct else -1
        cur_streak = s[3] if s else 0
        m_streak = s[4] if s else 0
        new_streak = cur_streak + 1 if is_correct else 0
        new_max = max(m_streak, new_streak)

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
        status = conn.execute("SELECT value FROM settings WHERE key='compliments_enabled'").fetchone()
        if not status or status[0] == '0': return None
        res = conn.execute("SELECT text FROM compliments WHERE type=? ORDER BY RANDOM() LIMIT 1", (c_type,)).fetchone()
        return res[0] if res else None

def get_leaderboard_data(chat_id=None, limit=25):
    with get_db() as conn:
        name_logic = "COALESCE(CASE WHEN u.username != '' THEN '@' || u.username END, u.first_name, 'Participant')"
        if chat_id:
            query = f"SELECT {name_logic}, gs.attempted, gs.correct, gs.score FROM group_stats gs LEFT JOIN users u ON gs.user_id = u.user_id WHERE gs.chat_id = ? ORDER BY gs.score DESC LIMIT ?"
            return conn.execute(query, (chat_id, limit)).fetchall()
        query = f"SELECT {name_logic}, s.attempted, s.correct, s.score FROM stats s LEFT JOIN users u ON s.user_id = u.user_id ORDER BY s.score DESC LIMIT ?"
        return conn.execute(query, (limit,)).fetchall()

if __name__ == "__main__":
    init_db()
    print("✅ Turso Ready.")
