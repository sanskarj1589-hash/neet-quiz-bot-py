import sqlite3
from datetime import datetime, timedelta

DB_NAME = "neetbot.db"

# -------------------- CONNECTION --------------------

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# -------------------- INIT DATABASE --------------------

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # USERS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        joined_at TIMESTAMP
    )
    """)

    # QUESTIONS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT,
        option_a TEXT,
        option_b TEXT,
        option_c TEXT,
        option_d TEXT,
        correct_option INTEGER,
        explanation TEXT,
        added_by INTEGER,
        created_at TIMESTAMP
    )
    """)

    # COMPLIMENTS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS compliments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT,
        added_by INTEGER,
        created_at TIMESTAMP
    )
    """)

    # CHAT SETTINGS (for /offcompliments)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_settings (
        chat_id INTEGER PRIMARY KEY,
        compliments_enabled INTEGER DEFAULT 1
    )
    """)

    # POLL HISTORY (for weekly stats & accuracy)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS poll_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        chat_id INTEGER,
        question_id INTEGER,
        is_correct INTEGER,
        answered_at TIMESTAMP
    )
    """)

    # GLOBAL SCORES
    cur.execute("""
    CREATE TABLE IF NOT EXISTS scores_global (
        user_id INTEGER PRIMARY KEY,
        total_attempts INTEGER DEFAULT 0,
        total_correct INTEGER DEFAULT 0,
        current_correct_streak INTEGER DEFAULT 0,
        best_correct_streak INTEGER DEFAULT 0
    )
    """)

    # GROUP SCORES
    cur.execute("""
    CREATE TABLE IF NOT EXISTS scores_group (
        chat_id INTEGER,
        user_id INTEGER,
        attempts INTEGER DEFAULT 0,
        correct INTEGER DEFAULT 0,
        PRIMARY KEY (chat_id, user_id)
    )
    """)

    conn.commit()
    conn.close()
# -------------------- USERS --------------------

def ensure_user(user_id, username=None, first_name=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at)
    VALUES (?, ?, ?, ?)
    """, (user_id, username, first_name, datetime.utcnow()))
    conn.commit()
    conn.close()


# -------------------- QUESTIONS --------------------

def add_question(question, a, b, c, d, correct, explanation, added_by):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO questions (
        question, option_a, option_b, option_c, option_d,
        correct_option, explanation, added_by, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        question, a, b, c, d,
        correct, explanation, added_by, datetime.utcnow()
    ))
    conn.commit()
    conn.close()


def get_random_question():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row


def get_all_questions():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM questions ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_all_questions():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM questions")
    conn.commit()
    conn.close()


# -------------------- COMPLIMENTS --------------------

def add_compliment(text, added_by):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO compliments (text, added_by, created_at)
    VALUES (?, ?, ?)
    """, (text, added_by, datetime.utcnow()))
    conn.commit()
    conn.close()


def get_random_compliment():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT text FROM compliments ORDER BY RANDOM() LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_all_compliments():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, text FROM compliments ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_compliment(cid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM compliments WHERE id = ?", (cid,))
    conn.commit()
    conn.close()


# -------------------- CHAT SETTINGS --------------------

def set_compliments(chat_id, enabled: bool):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO chat_settings (chat_id, compliments_enabled)
    VALUES (?, ?)
    ON CONFLICT(chat_id) DO UPDATE SET compliments_enabled=excluded.compliments_enabled
    """, (chat_id, int(enabled)))
    conn.commit()
    conn.close()


def compliments_allowed(chat_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT compliments_enabled FROM chat_settings WHERE chat_id = ?
    """, (chat_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row[0]) if row else True

# -------------------- STATS HELPERS --------------------

def get_or_create_global_stats(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR IGNORE INTO stats_global (user_id)
    VALUES (?)
    """, (user_id,))
    conn.commit()

    cur.execute("SELECT * FROM stats_global WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row)


def update_attempt(user_id, is_correct: bool):
    stats = get_or_create_global_stats(user_id)

    today = date.today().isoformat()
    last_date = stats["last_attempt_date"]

    # -------- DAILY STREAK --------
    if last_date == today:
        daily_streak = stats["daily_streak"]
    elif last_date == (date.today() - timedelta(days=1)).isoformat():
        daily_streak = stats["daily_streak"] + 1
    else:
        daily_streak = 1

    # -------- CORRECT STREAK --------
    if is_correct:
        current_streak = stats["current_streak"] + 1
        best_streak = max(stats["best_streak"], current_streak)
    else:
        current_streak = 0
        best_streak = stats["best_streak"]

    max_streak = max(stats["max_streak"], daily_streak)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    UPDATE stats_global SET
        attempted = attempted + 1,
        correct = correct + ?,
        incorrect = incorrect + ?,
        score = score + ?,
        current_streak = ?,
        best_streak = ?,
        daily_streak = ?,
        max_streak = ?,
        last_attempt_date = ?
    WHERE user_id = ?
    """, (
        1 if is_correct else 0,
        0 if is_correct else 1,
        4 if is_correct else -1,
        current_streak,
        best_streak,
        daily_streak,
        max_streak,
        today,
        user_id
    ))
    conn.commit()
    conn.close()

    return current_streak


# -------------------- WEEKLY STATS --------------------

def get_weekly_stats(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT COUNT(*) as attempts,
           SUM(correct) as correct
    FROM stats_global
    WHERE user_id = ?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row or not row["attempts"]:
        return {"attempts": 0, "accuracy": 0.0}

    accuracy = (row["correct"] / row["attempts"]) * 100
    return {
        "attempts": row["attempts"],
        "accuracy": round(accuracy, 2)
    }


# -------------------- LEADERBOARDS --------------------

def get_global_leaderboard(limit=10):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT u.first_name, s.score
    FROM stats_global s
    JOIN users u ON u.user_id = s.user_id
    ORDER BY s.score DESC
    LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_group_leaderboard(chat_id, limit=10):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT u.first_name, g.score
    FROM stats_group g
    JOIN users u ON u.user_id = g.user_id
    WHERE g.chat_id = ?
    ORDER BY g.score DESC
    LIMIT ?
    """, (chat_id, limit))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_global_rank(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT COUNT(*) + 1 FROM stats_global
    WHERE score > (SELECT score FROM stats_global WHERE user_id = ?)
    """, (user_id,))
    rank = cur.fetchone()[0]
    conn.close()
    return rank


def get_group_rank(chat_id, user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    SELECT COUNT(*) + 1 FROM stats_group
    WHERE chat_id = ?
      AND score > (SELECT score FROM stats_group WHERE chat_id = ? AND user_id = ?)
    """, (chat_id, chat_id, user_id))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None
