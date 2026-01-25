import sqlite3
from contextlib import contextmanager
from datetime import datetime, date

DB_NAME = "neetiqbot.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            type TEXT,
            compliments_off INTEGER DEFAULT 0,
            autoquiz INTEGER DEFAULT 0
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            options TEXT,
            correct INTEGER,
            explanation TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS polls (
            poll_id TEXT PRIMARY KEY,
            question_id INTEGER,
            correct INTEGER,
            chat_id INTEGER
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            user_id INTEGER,
            chat_id INTEGER,
            question_id INTEGER,
            correct INTEGER,
            date TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS streaks (
            user_id INTEGER PRIMARY KEY,
            current INTEGER DEFAULT 0,
            best INTEGER DEFAULT 0,
            daily INTEGER DEFAULT 0,
            last_date TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS compliments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            text TEXT
        )
        """)
# ---------- USERS & GROUPS ----------

def add_user(user_id, username, name):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
            (user_id, username, name)
        )


def add_group(chat_id, title, chat_type):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO groups (chat_id, title, type) VALUES (?, ?, ?)",
            (chat_id, title, chat_type)
        )


def get_all_users():
    with get_conn() as conn:
        return [r["user_id"] for r in conn.execute("SELECT user_id FROM users")]


def get_all_groups():
    with get_conn() as conn:
        return [r["chat_id"] for r in conn.execute("SELECT chat_id FROM groups")]


# ---------- ADMINS ----------

def add_admin(user_id):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO admins VALUES (?)", (user_id,))


def remove_admin(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM admins WHERE user_id=?", (user_id,))


def is_admin(user_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM admins WHERE user_id=?",
            (user_id,)
        ).fetchone() is not None


def get_admins():
    with get_conn() as conn:
        return [r["user_id"] for r in conn.execute("SELECT user_id FROM admins")]



# ---------- QUESTIONS ----------

def add_question(question, options, correct, explanation):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO questions (question, options, correct, explanation) VALUES (?, ?, ?, ?)",
            (question, "|".join(options), correct, explanation)
        )


def delete_all_questions():
    with get_conn() as conn:
        conn.execute("DELETE FROM questions")


def count_questions():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]


def count_attempted_questions():
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(DISTINCT question_id) FROM attempts"
        ).fetchone()[0]


def get_random_question(chat_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM questions ORDER BY RANDOM() LIMIT 1"
        ).fetchone()

        if not row:
            return None

        return (
            row["id"],
            row["question"],
            row["options"].split("|"),
            row["correct"]
        )


# ---------- POLLS ----------

def register_poll(poll_id, question_id, chat_id):
    with get_conn() as conn:
        correct = conn.execute(
            "SELECT correct FROM questions WHERE id=?",
            (question_id,)
        ).fetchone()["correct"]

        conn.execute(
            "INSERT OR REPLACE INTO polls VALUES (?, ?, ?, ?)",
            (poll_id, question_id, correct, chat_id)
        )


def get_poll(poll_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT question_id, correct, chat_id FROM polls WHERE poll_id=?",
            (poll_id,)
        ).fetchone()

        return row if row else None

# ---------- ATTEMPTS ----------

def record_attempt(user_id, chat_id, question_id, correct):
    today = date.today().isoformat()

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO attempts VALUES (?, ?, ?, ?, ?)",
            (user_id, chat_id, question_id, int(correct), today)
        )


def increment_streak(user_id):
    today = date.today().isoformat()

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM streaks WHERE user_id=?",
            (user_id,)
        ).fetchone()

        if not row:
            conn.execute(
                "INSERT INTO streaks VALUES (?, 1, 1, 1, ?)",
                (user_id, today)
            )
            return

        current = row["current"] + 1
        best = max(row["best"], current)

        daily = row["daily"] + 1 if row["last_date"] == today else 1

        conn.execute(
            "UPDATE streaks SET current=?, best=?, daily=?, last_date=? WHERE user_id=?",
            (current, best, daily, today, user_id)
        )


def reset_streak(user_id):
    today = date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE streaks SET current=0, daily=0, last_date=? WHERE user_id=?",
            (today, user_id)
        )


def get_user_stats(user_id):
    with get_conn() as conn:
        stats = conn.execute("""
        SELECT
            COUNT(*) as attempted,
            SUM(correct) as correct
        FROM attempts WHERE user_id=?
        """, (user_id,)).fetchone()

        streak = conn.execute(
            "SELECT * FROM streaks WHERE user_id=?",
            (user_id,)
        ).fetchone()

        if not stats:
            return None

        return {
            "attempted": stats["attempted"],
            "correct": stats["correct"] or 0,
            "wrong": stats["attempted"] - (stats["correct"] or 0),
            "best_streak": streak["best"] if streak else 0,
            "daily_streak": streak["daily"] if streak else 0,
            "max_streak": streak["best"] if streak else 0,
            "score": (stats["correct"] or 0) * 4
        }

# ---------- LEADERBOARDS ----------

def get_global_leaderboard(limit=25):
    with get_conn() as conn:
        return conn.execute("""
        SELECT u.name,
               COUNT(a.question_id) as attempted,
               SUM(a.correct) as correct,
               SUM(a.correct)*4 as score
        FROM attempts a
        JOIN users u ON a.user_id=u.user_id
        GROUP BY a.user_id
        ORDER BY score DESC
        LIMIT ?
        """, (limit,)).fetchall()


def get_group_leaderboard(chat_id, limit=25):
    with get_conn() as conn:
        return conn.execute("""
        SELECT u.name,
               COUNT(a.question_id) as attempted,
               SUM(a.correct) as correct,
               SUM(a.correct)*4 as score
        FROM attempts a
        JOIN users u ON a.user_id=u.user_id
        WHERE a.chat_id=?
        GROUP BY a.user_id
        ORDER BY score DESC
        LIMIT ?
        """, (chat_id, limit)).fetchall()


# ---------- COMPLIMENTS ----------

def add_compliment(ctype, text):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO compliments (type, text) VALUES (?, ?)",
            (ctype, text)
        )


def delete_compliment(cid):
    with get_conn() as conn:
        conn.execute("DELETE FROM compliments WHERE id=?", (cid,))


def list_compliments():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM compliments").fetchall()


def get_compliment(correct):
    ctype = "correct" if correct else "wrong"
    with get_conn() as conn:
        row = conn.execute(
            "SELECT text FROM compliments WHERE type=? ORDER BY RANDOM() LIMIT 1",
            (ctype,)
        ).fetchone()
        return row["text"] if row else None


def set_compliments_off(chat_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE groups SET compliments_off=1 WHERE chat_id=?",
            (chat_id,)
        )


def is_compliments_off(chat_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT compliments_off FROM groups WHERE chat_id=?",
            (chat_id,)
        ).fetchone()
        return row and row["compliments_off"] == 1


# ---------- AUTO QUIZ ----------

def enable_autoquiz(chat_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE groups SET autoquiz=1 WHERE chat_id=?",
            (chat_id,)
        )


def get_autoquiz_groups():
    with get_conn() as conn:
        return [
            r["chat_id"]
            for r in conn.execute("SELECT chat_id FROM groups WHERE autoquiz=1")
        ]


# ---------- BOT STATS ----------

def count_users():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def count_groups():
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]


def count_attempted_users():
    with get_conn() as conn:
        return conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM attempts"
        ).fetchone()[0]


def get_bot_stats():
    return {
        "users": count_users(),
        "groups": count_groups(),
        "questions": count_questions(),
        "attempted_users": count_attempted_users()
    }


