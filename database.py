import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from datetime import datetime, date

# On Render, DATABASE_URL is automatically provided in Environment Variables
DATABASE_URL = os.environ.get('DATABASE_URL')

@contextmanager
def get_db():
    # Use sslmode='require' for secure cloud connections
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    # cursor_factory=RealDictCursor makes results behave like dictionaries
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        yield cur
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def init_db():
    with get_db() as cur:
        # --- 1. CORE SYSTEM TABLES ---
        cur.execute("""CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            question TEXT, a TEXT, b TEXT, c TEXT, d TEXT,
            correct TEXT, explanation TEXT)""")

        cur.execute("""CREATE TABLE IF NOT EXISTS active_polls (
            poll_id TEXT PRIMARY KEY,
            chat_id BIGINT,
            correct_option_id INTEGER)""")

        # --- 2. USER & GROUP REGISTRATION ---
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TEXT)""")

        cur.execute("""CREATE TABLE IF NOT EXISTS chats (
            chat_id BIGINT PRIMARY KEY,
            type TEXT,
            title TEXT,
            added_at TEXT)""")

        cur.execute("CREATE TABLE IF NOT EXISTS admins (user_id BIGINT PRIMARY KEY, added_at TEXT)")

        # --- 3. STATS & SCORING ---
        cur.execute("""CREATE TABLE IF NOT EXISTS stats (
            user_id BIGINT PRIMARY KEY,
            attempted INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0,
            score INTEGER DEFAULT 0,
            current_streak INTEGER DEFAULT 0,
            max_streak INTEGER DEFAULT 0,
            last_date TEXT)""")

        cur.execute("""CREATE TABLE IF NOT EXISTS group_stats (
            chat_id BIGINT,
            user_id BIGINT,
            score INTEGER DEFAULT 0,
            attempted INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id))""")

        # --- 4. COMPLIMENTS & GROUP CUSTOMIZATION ---
        cur.execute("""CREATE TABLE IF NOT EXISTS compliments (
            id SERIAL PRIMARY KEY,
            type TEXT,
            text TEXT)""")

        cur.execute("""CREATE TABLE IF NOT EXISTS group_compliments (
            chat_id BIGINT,
            type TEXT,
            text TEXT)""")

        cur.execute("""CREATE TABLE IF NOT EXISTS group_settings (
            chat_id BIGINT PRIMARY KEY,
            compliments_enabled INTEGER DEFAULT 1)""")

        # --- 5. GLOBAL BOT SETTINGS ---
        cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        
        defaults = [
            ('footer_text', 'NEETIQBot'),
            ('footer_enabled', '1'),
            ('autoquiz_enabled', '0'),
            ('autoquiz_interval', '30')
        ]
        for key, val in defaults:
            cur.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", (key, val))

def update_user_stats(user_id, chat_id, is_correct):
    today = str(date.today())
    points = 4 if is_correct else -1
    
    with get_db() as cur:
        cur.execute("INSERT INTO stats (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (user_id,))
        
        cur.execute("SELECT * FROM stats WHERE user_id=%s", (user_id,))
        s = cur.fetchone()

        new_streak = s['current_streak'] + 1 if is_correct else 0
        new_max = max(s['max_streak'], new_streak)

        cur.execute("""UPDATE stats SET attempted=attempted+1, correct=correct+%s,
                     score=score+%s, current_streak=%s, max_streak=%s, last_date=%s
                     WHERE user_id=%s""", (1 if is_correct else 0, points, new_streak, new_max, today, user_id))
        
        if chat_id < 0:
            cur.execute("INSERT INTO group_stats (chat_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (chat_id, user_id))
            cur.execute("""UPDATE group_stats SET score=score+%s, attempted=attempted+1,
                         correct=correct+%s WHERE chat_id=%s AND user_id=%s""",
                        (points, 1 if is_correct else 0, chat_id, user_id))

def get_leaderboard_data(chat_id=None, limit=25):
    with get_db() as cur:
        if chat_id:
            # Join with users table to get the first_name for the leaderboard
            cur.execute("""SELECT u.first_name, gs.attempted, gs.correct, gs.score
                        FROM group_stats gs JOIN users u ON gs.user_id = u.user_id
                        WHERE gs.chat_id = %s ORDER BY gs.score DESC LIMIT %s""", (chat_id, limit))
        else:
            cur.execute("""SELECT u.first_name, s.attempted, s.correct, s.score
                        FROM stats s JOIN users u ON s.user_id = u.user_id
                        ORDER BY s.score DESC LIMIT %s""", (limit,))
        return cur.fetchall()

if __name__ == "__main__":
    init_db()
    print("✅ PostgreSQL Database Layer Ready.")
                                                                                                           
