import sqlite3
import random
from contextlib import contextmanager
from datetime import datetime, date

DB_NAME = "neetiq_master.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
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
    with get_db() as conn:
        # 1. Sync User Info (This is the most important part!)
        conn.execute("""
            INSERT INTO users (user_id, username, first_name) 
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                username = excluded.username, 
                first_name = excluded.first_name
        """, (user_id, username, first_name))

        # 2. Update Global Stats
        conn.execute("""
            INSERT INTO stats (user_id, attempted, correct, score) 
            VALUES (?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                attempted = attempted + 1,
                correct = correct + (CASE WHEN ? THEN 1 ELSE 0 END),
                score = score + (CASE WHEN ? THEN 4 ELSE -1 END)
        """, (user_id, 1 if is_correct else 0, 4 if is_correct else -1, is_correct, is_correct))

        # 3. Update Group Stats (if chat_id provided)
        if chat_id:
            conn.execute("""
                INSERT INTO group_stats (user_id, chat_id, attempted, correct, score) 
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET 
                    attempted = attempted + 1,
                    correct = correct + (CASE WHEN ? THEN 1 ELSE 0 END),
                    score = score + (CASE WHEN ? THEN 4 ELSE -1 END)
            """, (user_id, chat_id, 1 if is_correct else 0, 4 if is_correct else -1, is_correct, is_correct))


def get_compliment(c_type):
    with get_db() as conn:
        status = conn.execute("SELECT value FROM settings WHERE key='compliments_enabled'").fetchone()[0]
        if status == '0': return None
        res = conn.execute("SELECT text FROM compliments WHERE type=? ORDER BY RANDOM() LIMIT 1", (c_type,)).fetchone()
        return res[0] if res else None

def get_leaderboard_data(chat_id=None, limit=25):
    """Simplified query that picks the best name directly from SQL."""
    with get_db() as conn:
        # COALESCE picks the first non-null value: Username -> First Name -> ID
        name_sql = """
            COALESCE(
                CASE WHEN u.username IS NOT NULL AND u.username != '' THEN '@' || u.username ELSE NULL END,
                u.first_name,
                'Participant ' || s.user_id
            ) AS display_name
        """
        
        if chat_id:
            query = f"SELECT {name_sql}, gs.attempted, gs.correct, gs.score FROM group_stats gs LEFT JOIN users u ON gs.user_id = u.user_id WHERE gs.chat_id = ? ORDER BY gs.score DESC LIMIT ?"
            return conn.execute(query, (chat_id, limit)).fetchall()
        else:
            query = f"SELECT {name_sql}, s.attempted, s.correct, s.score FROM stats s LEFT JOIN users u ON s.user_id = u.user_id ORDER BY s.score DESC LIMIT ?"
            return conn.execute(query, (limit,)).fetchall()

def get_user_display_name(user_id):
    """Directly fetches the name from the users table for name recovery."""
    with get_db() as conn:
        row = conn.execute("SELECT username, first_name FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            if row[0]: return f"@{row[0]}"
            if row[1]: return row[1]
        return f"Participant {user_id}"


if __name__ == "__main__":
    init_db()
    print("✅ Database Master Layer Ready.")

