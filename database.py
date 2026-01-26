#!/usr/bin/env python3
"""
database.py — NEETIQBot
Stable function-based SQLite database layer
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
import random

DB_NAME = "neetquiz.db"


# -------------------------
# DB context manager
# -------------------------
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# -------------------------
# INIT DB
# -------------------------
def init_db():
    with get_db() as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        # USERS
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TEXT
        )
        """)

        # CHATS
        conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            type TEXT,
            title TEXT,
            added_at TEXT
        )
        """)

        # ADMINS
        conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            added_at TEXT
        )
        """)

        # QUESTIONS
        conn.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            a TEXT NOT NULL,
            b TEXT NOT NULL,
            c TEXT NOT NULL,
            d TEXT NOT NULL,
            correct TEXT NOT NULL CHECK (correct IN ('A','B','C','D')),
            explanation TEXT
        )
        """)

        # SENT QUESTIONS
        conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_questions (
            chat_id INTEGER,
            question_id INTEGER,
            sent_at TEXT,
            PRIMARY KEY (chat_id, question_id)
        )
        """)

        # SETTINGS
        conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        # ✅ GLOBAL SCORES + STREAKS
        conn.execute("""
        CREATE TABLE IF NOT EXISTS scores_global (
            user_id INTEGER PRIMARY KEY,

            attempted INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0,
            incorrect INTEGER DEFAULT 0,
            score INTEGER DEFAULT 0,

            current_streak INTEGER DEFAULT 0,
            best_streak INTEGER DEFAULT 0,

            daily_streak INTEGER DEFAULT 0,
            max_streak INTEGER DEFAULT 0,
            last_attempt_date TEXT
        )
        """)

        conn.commit()

    init_footer()
    print("✅ Database initialized successfully")


# -------------------------
# USERS / CHATS
# -------------------------
def add_user(user_id, username=None, first_name=None):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users VALUES (?,?,?,?)",
            (user_id, username, first_name, datetime.utcnow().isoformat())
        )


def add_chat(chat_id, chat_type=None, title=None):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO chats VALUES (?,?,?,?)",
            (chat_id, chat_type, title, datetime.utcnow().isoformat())
        )


# -------------------------
# ADMINS
# -------------------------
def is_admin(user_id):
    with get_db() as conn:
        return conn.execute(
            "SELECT 1 FROM admins WHERE user_id=?",
            (user_id,)
        ).fetchone() is not None


def add_admin(user_id):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO admins VALUES (?,?)",
            (user_id, datetime.utcnow().isoformat())
        )


def remove_admin(user_id):
    with get_db() as conn:
        conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))


def list_admins():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM admins")]


# -------------------------
# QUESTIONS (CRITICAL FIX)
# -------------------------
def get_unused_question_ids_for_chat(chat_id, limit=1):
    with get_db() as conn:
        rows = conn.execute("""
        SELECT id FROM questions
        WHERE id NOT IN (
            SELECT question_id FROM sent_questions WHERE chat_id=?
        )
        ORDER BY RANDOM()
        LIMIT ?
        """, (chat_id, limit)).fetchall()
        return [r["id"] for r in rows]


def get_question_by_id(qid):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM questions WHERE id=?",
            (qid,)
        ).fetchone()
        return dict(row) if row else None


def mark_question_sent(chat_id, qid):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sent_questions VALUES (?,?,?)",
            (chat_id, qid, datetime.utcnow().isoformat())
        )


def delete_question(qid):
    with get_db() as conn:
        conn.execute("DELETE FROM questions WHERE id=?", (qid,))


def add_question(question, a, b, c, d, correct, explanation=None):
    with get_db() as conn:
        conn.execute("""
        INSERT INTO questions
        (question,a,b,c,d,correct,explanation)
        VALUES (?,?,?,?,?,?,?)
        """, (question, a, b, c, d, correct, explanation))


def get_question_count():
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]


# -------------------------
# COMPLIMENTS
# -------------------------
def add_compliment(type_, text):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO compliments (type,text) VALUES (?,?)",
            (type_, text)
        )


def get_random_compliment(type_):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT text FROM compliments WHERE type=?",
            (type_,)
        ).fetchall()
        return random.choice(rows)["text"] if rows else None


# -------------------------
# SETTINGS
# -------------------------
def get_setting(key, default=None):
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?",
            (key,)
        ).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with get_db() as conn:
        conn.execute("""
        INSERT INTO settings VALUES (?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, value))

def increment_attempted_questions():
    with get_db() as conn:
        conn.execute("""
            INSERT INTO settings (key, value)
            VALUES ('questions_attempted', '1')
            ON CONFLICT(key)
            DO UPDATE SET value = CAST(value AS INTEGER) + 1
        """)


def get_attempted_questions():
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='questions_attempted'"
        ).fetchone()
        return int(row["value"]) if row else 0

def get_questions_left():
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM questions"
        ).fetchone()
        return row["cnt"] if row else 0

def get_total_questions():
    left = get_questions_left()
    attempted = get_attempted_questions()
    return left + attempted

# -------------------------
# GLOBAL AUTO QUIZ
# -------------------------

def ensure_global_auto_quiz():
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('autoquiz_enabled', '0')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('autoquiz_interval', '30')"
        )


def set_global_autoquiz(enabled=None, interval=None):
    ensure_global_auto_quiz()
    with get_db() as conn:
        if enabled is not None:
            conn.execute(
                "UPDATE settings SET value=? WHERE key='autoquiz_enabled'",
                ("1" if enabled else "0",)
            )
        if interval is not None:
            conn.execute(
                "UPDATE settings SET value=? WHERE key='autoquiz_interval'",
                (str(interval),)
            )


def get_global_autoquiz():
    ensure_global_auto_quiz()
    with get_db() as conn:
        enabled = conn.execute(
            "SELECT value FROM settings WHERE key='autoquiz_enabled'"
        ).fetchone()["value"]

        interval = conn.execute(
            "SELECT value FROM settings WHERE key='autoquiz_interval'"
        ).fetchone()["value"]

    return {
        "enabled": enabled == "1",
        "interval": int(interval)
    }


    with get_db() as conn:
        rows = conn.execute(
            "SELECT chat_id FROM chats WHERE type IN ('group', 'supergroup')"
        ).fetchall()
        return [r["chat_id"] for r in rows]


# -------------------------
# SCORES
# -------------------------
def ensure_global_score(user_id):
    with get_db() as conn:
        conn.execute("""
        INSERT OR IGNORE INTO scores_global (
            user_id,
            attempted,
            correct,
            incorrect,
            score,
            current_streak,
            best_streak,
            max_streak,
            daily_streak,
            last_attempt_date
        ) VALUES (?, 0, 0, 0, 0, 0, 0, 0, 0, NULL)
        """, (user_id,))
        conn.commit()

def update_global_score(user_id, is_correct):
    ensure_global_score(user_id)

    with get_db() as conn:
        if is_correct:
            conn.execute("""
            UPDATE scores_global
            SET
                attempted = attempted + 1,
                correct = correct + 1,
                score = score + 4,
                current_streak = current_streak + 1,
                best_streak = MAX(best_streak, current_streak + 1)
            WHERE user_id=?
            """, (user_id,))
        else:
            conn.execute("""
            UPDATE scores_global
            SET
                attempted = attempted + 1,
                incorrect = incorrect + 1,
                score = score - 1,
                current_streak = 0
            WHERE user_id=?
            """, (user_id,))

        conn.commit()


def get_global_score(user_id):
    with get_db() as conn:
        row = conn.execute("""
        SELECT * FROM scores_global WHERE user_id=?
        """, (user_id,)).fetchone()
        return dict(row) if row else None

def get_global_user_stats(user_id):
    with get_db() as conn:
        row = conn.execute("""
        SELECT
            attempted,
            correct,
            incorrect,
            score,
            current_streak,
            best_streak,
            max_streak,
            daily_streak
        FROM scores_global
        WHERE user_id = ?
        """, (user_id,)).fetchone()

        if not row:
            return {
                "attempted": 0,
                "correct": 0,
                "incorrect": 0,
                "score": 0,
                "current_streak": 0,
                "best_streak": 0,
                "max_streak": 0,
                "daily_streak": 0
            }

        return dict(row)

def get_global_leaderboard(limit=25):
    with get_db() as conn:
        rows = conn.execute("""
        SELECT
            sg.user_id,
            u.first_name,
            u.username,
            sg.attempted,
            sg.correct,
            sg.score
        FROM scores_global sg
        LEFT JOIN users u ON sg.user_id = u.user_id
        ORDER BY sg.score DESC
        LIMIT ?
        """, (limit,)).fetchall()

        return [dict(r) for r in rows]

def get_group_leaderboard(chat_id, limit=10):
    with get_db() as conn:
        rows = conn.execute("""
        SELECT
            user_id,
            username,
            attempted,
            correct,
            score
        FROM group_stats
        WHERE chat_id = ?
        ORDER BY score DESC
        LIMIT ?
        """, (chat_id, limit)).fetchall()

        return [dict(r) for r in rows]


def update_group_score(chat_id, user_id, username, is_correct):
    with get_db() as conn:
        # ensure row exists
        conn.execute("""
        INSERT OR IGNORE INTO group_stats
        (chat_id, user_id, username, attempted, correct, incorrect, score)
        VALUES (?, ?, ?, 0, 0, 0, 0)
        """, (chat_id, user_id, username))

        if is_correct:
            conn.execute("""
            UPDATE group_stats
            SET attempted = attempted + 1,
                correct = correct + 1,
                score = score + 4
            WHERE chat_id = ? AND user_id = ?
            """, (chat_id, user_id))
        else:
            conn.execute("""
            UPDATE group_stats
            SET attempted = attempted + 1,
                incorrect = incorrect + 1,
                score = score - 1
            WHERE chat_id = ? AND user_id = ?
            """, (chat_id, user_id))

def get_global_rank(user_id):
    with get_db() as conn:
        user = conn.execute(
            "SELECT score FROM scores_global WHERE user_id=?",
            (user_id,)
        ).fetchone()
        if not user:
            return None

        rank = conn.execute(
            "SELECT COUNT(*) + 1 FROM scores_global WHERE score > ?",
            (user["score"],)
        ).fetchone()[0]

        return rank


def get_group_rank(chat_id, user_id):
    with get_db() as conn:
        user = conn.execute(
            "SELECT score FROM group_stats WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        ).fetchone()
        if not user:
            return None

        rank = conn.execute(
            """
            SELECT COUNT(*) + 1
            FROM group_stats
            WHERE chat_id=? AND score > ?
            """,
            (chat_id, user["score"])
        ).fetchone()[0]

        return rank

    with get_db() as conn:
        return conn.execute(
            "SELECT user_id FROM users"
        ).fetchall()

def get_all_users():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT user_id FROM users")]

    with get_db() as conn:
        return conn.execute(
            """
            SELECT chat_id
            FROM chats
            WHERE chat_type IN ('group', 'supergroup')
            """
        ).fetchall()

def get_all_groups():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT chat_id FROM chats WHERE type IN ('group', 'supergroup')"
        ).fetchall()
        return [r["chat_id"] for r in rows]

# ================= FOOTER SETTINGS =================

def init_footer():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS footer_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled INTEGER DEFAULT 1,
                text TEXT DEFAULT ''
            )
        """)
        row = conn.execute(
            "SELECT id FROM footer_settings WHERE id = 1"
        ).fetchone()

        if not row:
            conn.execute(
                "INSERT INTO footer_settings (id, enabled, text) VALUES (1, 1, '')"
            )
        conn.commit()


def get_footer():
    with get_db() as conn:
        row = conn.execute(
            "SELECT enabled, text FROM footer_settings WHERE id = 1"
        ).fetchone()

        return {
            "enabled": bool(row["enabled"]),
            "text": row["text"] or ""
        }


def set_footer_text(text: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE footer_settings SET text = ? WHERE id = 1",
            (text,)
        )
        conn.commit()


def set_footer_enabled(enabled: bool):
    with get_db() as conn:
        conn.execute(
            "UPDATE footer_settings SET enabled = ? WHERE id = 1",
            (1 if enabled else 0,)
        )
        conn.commit()

def get_total_users():
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM users"
        ).fetchone()
        return row["total"]


def get_total_groups():
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM chats"
        ).fetchone()
        return row["total"]


def get_total_questions():
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total FROM questions"
        ).fetchone()
        return row["total"]


def get_users_who_attempted():
    with get_db() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS total
            FROM scores_global
            WHERE attempted > 0
        """).fetchone()
        return row["total"]

# -------------------------
# MAIN
# -------------------------
