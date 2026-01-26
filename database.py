import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                score INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                last_active TIMESTAMP DEFAULT NOW()
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                chat_id BIGINT PRIMARY KEY,
                title TEXT,
                autoquiz_enabled BOOLEAN DEFAULT FALSE,
                autoquiz_interval INTEGER DEFAULT 30,
                last_autoquiz_time TIMESTAMP
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id BIGINT PRIMARY KEY
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id SERIAL PRIMARY KEY,
                question TEXT NOT NULL,
                options TEXT[] NOT NULL,
                correct_option INTEGER NOT NULL,
                explanation TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS sent_questions (
                question_id INTEGER,
                chat_id BIGINT,
                sent_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (question_id, chat_id)
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS compliments (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS group_scores (
                chat_id BIGINT,
                user_id BIGINT,
                score INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """)

          # ================= USERS =================

def add_or_update_user(user_id, username=None, first_name=None, last_name=None):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, last_active)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                last_active = NOW()
            """, (user_id, username, first_name, last_name))
            conn.commit()


def get_user(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            return cur.fetchone()


def update_user_score(user_id, delta):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            UPDATE users
            SET score = score + %s
            WHERE user_id = %s
            """, (delta, user_id))
            conn.commit()


def update_user_streak(user_id, streak):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            UPDATE users
            SET streak = %s
            WHERE user_id = %s
            """, (streak, user_id))
            conn.commit()


# ================= GROUPS =================

def add_or_update_group(chat_id, title):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO groups (chat_id, title)
            VALUES (%s, %s)
            ON CONFLICT (chat_id)
            DO UPDATE SET title = EXCLUDED.title
            """, (chat_id, title))
            conn.commit()


def get_group(chat_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM groups WHERE chat_id = %s", (chat_id,))
            return cur.fetchone()


def set_autoquiz(chat_id, enabled, interval):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            UPDATE groups
            SET autoquiz_enabled = %s,
                autoquiz_interval = %s
            WHERE chat_id = %s
            """, (enabled, interval, chat_id))
            conn.commit()


def update_last_autoquiz(chat_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            UPDATE groups
            SET last_autoquiz_time = NOW()
            WHERE chat_id = %s
            """, (chat_id,))
            conn.commit()


# ================= ADMINS =================

def add_admin(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO admins (user_id)
            VALUES (%s)
            ON CONFLICT DO NOTHING
            """, (user_id,))
            conn.commit()


def remove_admin(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM admins WHERE user_id = %s", (user_id,))
            conn.commit()


def is_admin(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM admins WHERE user_id = %s", (user_id,))
            return cur.fetchone() is not None
            conn.commit()
# ================= QUESTIONS =================

def add_question(question, options, correct_option, explanation=None):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO questions (question, options, correct_option, explanation)
            VALUES (%s, %s, %s, %s)
            """, (question, options, correct_option, explanation))
            conn.commit()


def get_random_question(chat_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT q.*
            FROM questions q
            WHERE NOT EXISTS (
                SELECT 1 FROM sent_questions s
                WHERE s.question_id = q.id
                AND s.chat_id = %s
            )
            ORDER BY RANDOM()
            LIMIT 1
            """, (chat_id,))
            return cur.fetchone()


def mark_question_sent(question_id, chat_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO sent_questions (question_id, chat_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """, (question_id, chat_id))
            conn.commit()


def get_total_questions():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM questions")
            row = cur.fetchone()
            return row["total"] if row else 0


def clear_sent_questions(chat_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sent_questions WHERE chat_id = %s", (chat_id,))
            conn.commit()

 # ================= SCORES & STREAKS =================

def update_group_score(chat_id, user_id, delta):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO group_scores (chat_id, user_id, score)
            VALUES (%s, %s, %s)
            ON CONFLICT (chat_id, user_id)
            DO UPDATE SET score = group_scores.score + %s
            """, (chat_id, user_id, delta, delta))
            conn.commit()


def get_user_group_score(chat_id, user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT score FROM group_scores
            WHERE chat_id = %s AND user_id = %s
            """, (chat_id, user_id))
            row = cur.fetchone()
            return row["score"] if row else 0


def reset_group_scores(chat_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM group_scores WHERE chat_id = %s", (chat_id,))
            conn.commit()


def update_streaks(user_id, correct):
    with get_db() as conn:
        with conn.cursor() as cur:
            if correct:
                cur.execute("""
                UPDATE users
                SET streak = streak + 1
                WHERE user_id = %s
                """, (user_id,))
            else:
                cur.execute("""
                UPDATE users
                SET streak = 0
                WHERE user_id = %s
                """, (user_id,))
            conn.commit()


# ================= LEADERBOARDS =================

def get_global_leaderboard(limit=10):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT user_id, username, first_name, score
            FROM users
            ORDER BY score DESC
            LIMIT %s
            """, (limit,))
            return cur.fetchall()


def get_group_leaderboard(chat_id, limit=10):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT u.user_id, u.username, u.first_name, g.score
            FROM group_scores g
            JOIN users u ON u.user_id = g.user_id
            WHERE g.chat_id = %s
            ORDER BY g.score DESC
            LIMIT %s
            """, (chat_id, limit))
            return cur.fetchall() 


# ================= COMPLIMENTS =================

def add_compliment(text):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO compliments (text)
            VALUES (%s)
            """, (text,))
            conn.commit()


def get_random_compliment():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT text FROM compliments
            ORDER BY RANDOM()
            LIMIT 1
            """)
            row = cur.fetchone()
            return row["text"] if row else "Well done!"


# ================= SETTINGS =================

def set_setting(key, value):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value
            """, (key, value))
            conn.commit()


def get_setting(key, default=None):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
            row = cur.fetchone()
            return row["value"] if row else default


# ================= STATS =================

def get_bot_stats():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total_users FROM users")
            users = cur.fetchone()["total_users"]

            cur.execute("SELECT COUNT(*) AS total_groups FROM groups")
            groups = cur.fetchone()["total_groups"]

            cur.execute("SELECT COUNT(*) AS total_questions FROM questions")
            questions = cur.fetchone()["total_questions"]

            return {
                "users": users,
                "groups": groups,
                "questions": questions
          }



