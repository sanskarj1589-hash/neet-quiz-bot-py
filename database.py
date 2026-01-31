import os
import libsql_client
from contextlib import contextmanager

# --- TURSO CONFIGURATION ---
TURSO_URL = os.environ.get("TURSO_URL")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN")

if not TURSO_URL or not TURSO_TOKEN:
    raise ValueError("❌ DATABASE ERROR: TURSO_URL or TURSO_TOKEN is not set in Render!")

@contextmanager
def get_db():
    """Sync client for Turso/libSQL"""
    client = libsql_client.create_client_sync(url=TURSO_URL, auth_token=TURSO_TOKEN)
    try:
        yield client
    finally:
        client.close()

def init_db():
    """Initializes tables with full Subject Tracking support."""
    with get_db() as conn:
        # 1. Questions Bank
        conn.execute("""CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT, a TEXT, b TEXT, c TEXT, d TEXT, 
            correct TEXT, explanation TEXT,
            subject TEXT DEFAULT 'General')""")

        # 2. Active Poll Tracker (Crucial for Scorecard)
        conn.execute("""CREATE TABLE IF NOT EXISTS active_polls (
            poll_id TEXT PRIMARY KEY, 
            chat_id INTEGER, 
            correct_option_id INTEGER,
            subject TEXT)""")

        # 3. User & Chat Registry
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            username TEXT, first_name TEXT, joined_at TEXT)""")
        
        conn.execute("""CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY, type TEXT, title TEXT, added_at TEXT)""")

        # 4. Global Stats (Updated with Subject Columns)
        conn.execute("""CREATE TABLE IF NOT EXISTS stats (
            user_id INTEGER PRIMARY KEY, 
            attempted INTEGER DEFAULT 0, correct INTEGER DEFAULT 0, score INTEGER DEFAULT 0,
            bio_att INTEGER DEFAULT 0, bio_cor INTEGER DEFAULT 0,
            phy_att INTEGER DEFAULT 0, phy_cor INTEGER DEFAULT 0,
            che_att INTEGER DEFAULT 0, che_cor INTEGER DEFAULT 0,
            current_streak INTEGER DEFAULT 0, max_streak INTEGER DEFAULT 0, last_date TEXT)""")

        # 5. Group Stats (Updated with Subject Columns)
        conn.execute("""CREATE TABLE IF NOT EXISTS group_stats (
            chat_id INTEGER, user_id INTEGER, score INTEGER DEFAULT 0, 
            attempted INTEGER DEFAULT 0, correct INTEGER DEFAULT 0,
            bio_att INTEGER DEFAULT 0, bio_cor INTEGER DEFAULT 0,
            phy_att INTEGER DEFAULT 0, phy_cor INTEGER DEFAULT 0,
            che_att INTEGER DEFAULT 0, che_cor INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id))""")
            
    print("✅ Database Tables Initialized Successfully!")
  

def update_user_stats(user_id, chat_id, is_correct, subject=None, username=None, first_name=None):
    """Updates global and group stats with subject-specific tracking."""
    score_change = 4 if is_correct else -1
    correct_inc = 1 if is_correct else 0
    
    # Identify which subject columns to update based on question text
    subj = str(subject).lower() if subject else ""
    s_prefix = "bio" if "bio" in subj else "phy" if "phy" in subj else "che" if "che" in subj else None

    with get_db() as conn:
        # 1. Update/Ensure User Info is stored
        conn.execute("""
            INSERT INTO users (user_id, username, first_name) 
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                username = excluded.username, first_name = excluded.first_name
        """, (user_id, username, first_name))

        # 2. Update Global Stats
        if s_prefix:
            # Updates both total stats AND subject-specific stats
            sql = f"""
                INSERT INTO stats (user_id, attempted, correct, score, {s_prefix}_att, {s_prefix}_cor) 
                VALUES (?, 1, ?, ?, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET 
                    attempted = attempted + 1, 
                    correct = correct + ?, 
                    score = score + ?,
                    {s_prefix}_att = {s_prefix}_att + 1, 
                    {s_prefix}_cor = {s_prefix}_cor + ?
            """
            conn.execute(sql, (user_id, correct_inc, score_change, correct_inc, correct_inc, score_change, correct_inc))
        else:
            # Standard update for 'General' questions
            conn.execute("""
                INSERT INTO stats (user_id, attempted, correct, score) 
                VALUES (?, 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET 
                    attempted = attempted + 1, correct = correct + ?, score = score + ?
            """, (user_id, correct_inc, score_change, correct_inc, score_change))

        # 3. Update Group Stats (if the quiz happened in a group)
        if chat_id:
            if s_prefix:
                sql_grp = f"""
                    INSERT INTO group_stats (user_id, chat_id, attempted, correct, score, {s_prefix}_att, {s_prefix}_cor) 
                    VALUES (?, ?, 1, ?, ?, 1, ?)
                    ON CONFLICT(user_id, chat_id) DO UPDATE SET 
                        attempted = attempted + 1, 
                        correct = correct + ?, 
                        score = score + ?,
                        {s_prefix}_att = {s_prefix}_att + 1, 
                        {s_prefix}_cor = {s_prefix}_cor + ?
                """
                conn.execute(sql_grp, (user_id, chat_id, correct_inc, score_change, correct_inc, correct_inc, score_change, correct_inc))
            else:
                conn.execute("""
                    INSERT INTO group_stats (user_id, chat_id, attempted, correct, score) 
                    VALUES (?, ?, 1, ?, ?)
                    ON CONFLICT(user_id, chat_id) DO UPDATE SET 
                        attempted = attempted + 1, correct = correct + ?, score = score + ?
                """, (user_id, chat_id, correct_inc, score_change, correct_inc, score_change))

def get_leaderboard_data(chat_id=None, limit=25):
    """Fetches global or group leaderboard with proper name formatting."""
    with get_db() as conn:
        # Professional name formatting: Priority Username > First Name > ID
        name_sql = """
            COALESCE(
                CASE WHEN u.username IS NOT NULL AND u.username != '' THEN '@' || u.username ELSE NULL END,
                u.first_name,
                'Aspirant ' || stats_table.user_id
            ) AS display_name
        """
        if chat_id:
            query = f"SELECT {name_sql.replace('stats_table', 'gs')}, gs.score FROM group_stats gs LEFT JOIN users u ON gs.user_id = u.user_id WHERE gs.chat_id = ? ORDER BY gs.score DESC LIMIT ?"
            return conn.execute(query, (chat_id, limit)).fetchall()
        else:
            query = f"SELECT {name_sql.replace('stats_table', 's')}, s.score FROM stats s LEFT JOIN users u ON s.user_id = u.user_id ORDER BY s.score DESC LIMIT ?"
            return conn.execute(query, (limit,)).fetchall()

def get_user_rank(user_id):
    """Calculates the global rank of a user based on score."""
    with get_db() as conn:
        res = conn.execute("SELECT COUNT(*) + 1 FROM stats WHERE score > (SELECT score FROM stats WHERE user_id = ?)", (user_id,)).fetchone()
        return res[0] if res else "N/A"

def get_group_user_rank(chat_id, user_id):
    """Calculates the rank of a user within a specific group."""
    with get_db() as conn:
        res = conn.execute("SELECT COUNT(*) + 1 FROM group_stats WHERE chat_id = ? AND score > (SELECT score FROM group_stats WHERE chat_id = ? AND user_id = ?)", (chat_id, chat_id, user_id)).fetchone()
        return res[0] if res else "N/A"
        
