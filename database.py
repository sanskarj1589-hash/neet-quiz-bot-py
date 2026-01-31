import os
import asyncio
import libsql_client
from contextlib import asynccontextmanager
from datetime import datetime

# --- CONFIGURATION ---
TURSO_URL = os.environ.get("TURSO_URL")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN")

# --- TURSO ASYNC COMPATIBILITY LAYER ---
class RowWrapper:
    """Mimics sqlite3.Row for async Turso results."""
    def __init__(self, row, columns):
        self.row = row
        self.columns = columns
    def __getitem__(self, key):
        if isinstance(key, str): return self.row[self.columns.index(key)]
        return self.row[key]
    def __iter__(self): return iter(self.row)

class TursoCursor:
    def __init__(self, client):
        self.client = client
    
    async def execute(self, sql, params=()):
        # MUST await the execution in the new library version
        res = await self.client.execute(sql, params)
        self.rows = [RowWrapper(r, res.columns) for r in res.rows]
        return self
    
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows

class TursoClientWrapper:
    def __init__(self, url, token):
        self.client = libsql_client.create_client(url=url, auth_token=token)
    def cursor(self): return TursoCursor(self.client)
    async def close(self): await self.client.close()

@asynccontextmanager
async def get_db():
    """Async context manager for Turso connections."""
    client = TursoClientWrapper(TURSO_URL, TURSO_TOKEN)
    try:
        yield client.cursor()
    finally:
        await client.close()


# --- INITIALIZATION & MIGRATION ---
async def init_db():
    """Asynchronous database initialization."""
    async with get_db() as conn:
        # 1. Create Core Tables (using await for every command)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id TEXT UNIQUE,
                message_id INTEGER,
                chat_id INTEGER,
                question TEXT,
                subject TEXT DEFAULT 'General',
                correct_option_id INTEGER
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS active_polls (
                poll_id TEXT PRIMARY KEY, 
                chat_id INTEGER, 
                correct_option_id INTEGER
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, 
                username TEXT, 
                first_name TEXT, 
                joined_at TEXT,
                source TEXT DEFAULT 'Group',
                status TEXT DEFAULT 'active'
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY, 
                type TEXT, 
                title TEXT, 
                added_at TEXT,
                status TEXT DEFAULT 'active'
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                user_id INTEGER PRIMARY KEY, 
                score INTEGER DEFAULT 0, 
                correct INTEGER DEFAULT 0, 
                attempted INTEGER DEFAULT 0,
                current_streak INTEGER DEFAULT 0,
                max_streak INTEGER DEFAULT 0,
                bio_att INTEGER DEFAULT 0, bio_cor INTEGER DEFAULT 0,
                phy_att INTEGER DEFAULT 0, phy_cor INTEGER DEFAULT 0,
                che_att INTEGER DEFAULT 0, che_cor INTEGER DEFAULT 0
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_stats (
                user_id INTEGER, 
                chat_id INTEGER, 
                score INTEGER DEFAULT 0, 
                correct INTEGER DEFAULT 0, 
                attempted INTEGER DEFAULT 0,
                bio_att INTEGER DEFAULT 0, bio_cor INTEGER DEFAULT 0,
                phy_att INTEGER DEFAULT 0, phy_cor INTEGER DEFAULT 0,
                che_att INTEGER DEFAULT 0, che_cor INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        await conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await conn.execute("CREATE TABLE IF NOT EXISTS compliments (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, text TEXT)")

        # 2. Migration Logic
        migrations = [
            ("users", "source TEXT DEFAULT 'Group'"),
            ("users", "status TEXT DEFAULT 'active'"),
            ("chats", "status TEXT DEFAULT 'active'"),
            ("questions", "subject TEXT DEFAULT 'General'"),
            ("questions", "correct_option_id INTEGER"),
            ("stats", "current_streak INTEGER DEFAULT 0"),
            ("stats", "max_streak INTEGER DEFAULT 0"),
            ("stats", "bio_att INTEGER DEFAULT 0"), ("stats", "bio_cor INTEGER DEFAULT 0"),
            ("stats", "phy_att INTEGER DEFAULT 0"), ("stats", "phy_cor INTEGER DEFAULT 0"),
            ("stats", "che_att INTEGER DEFAULT 0"), ("stats", "che_cor INTEGER DEFAULT 0"),
            ("group_stats", "bio_att INTEGER DEFAULT 0"), ("group_stats", "bio_cor INTEGER DEFAULT 0"),
            ("group_stats", "phy_att INTEGER DEFAULT 0"), ("group_stats", "phy_cor INTEGER DEFAULT 0"),
            ("group_stats", "che_att INTEGER DEFAULT 0"), ("group_stats", "che_cor INTEGER DEFAULT 0")
        ]

        for table, col_def in migrations:
            try:
                await conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
            except:
                pass 

        # 3. Default Settings
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_quiz', 'on')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('autoquiz_interval', '30')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('total_sent', '0')")
        
    print("✅ Database Verified and Synchronized (Async Mode).")
    


# --- QUESTION MANAGEMENT ---
def add_question(poll_id, message_id, chat_id, subject='General'):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO questions (poll_id, message_id, chat_id, subject) VALUES (?, ?, ?, ?)",
            (poll_id, message_id, chat_id, subject)
        )

def get_question_count():
    """Returns inventory for the /questions command"""
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) as count FROM questions").fetchone()['count']
        bio = conn.execute("SELECT COUNT(*) as count FROM questions WHERE subject='Bio'").fetchone()['count']
        phy = conn.execute("SELECT COUNT(*) as count FROM questions WHERE subject='Phy'").fetchone()['count']
        che = conn.execute("SELECT COUNT(*) as count FROM questions WHERE subject='Che'").fetchone()['count']
        return {"total": total, "bio": bio, "phy": phy, "che": che}

def get_question(poll_id):
    with get_db() as conn:
        return conn.execute("SELECT * FROM questions WHERE poll_id = ?", (poll_id,)).fetchone()

def delete_question(poll_id):
    with get_db() as conn:
        conn.execute("DELETE FROM questions WHERE poll_id = ?", (poll_id,))

# --- SCORE & STATS LOGIC ---
def update_user_stats(user_id, is_correct, subject='General'):
    with get_db() as conn:
        # 1. Update Global Stats
        col_att = "attempted"
        col_cor = "correct"
        
        # Map subject to specific columns
        subj_map = {
            'Bio': ('bio_att', 'bio_cor'),
            'Phy': ('phy_att', 'phy_cor'),
            'Che': ('che_att', 'che_cor')
        }
        
        # Base update
        sql = f"UPDATE stats SET {col_att} = {col_att} + 1"
        if is_correct:
            sql += f", {col_cor} = {col_cor} + 1, score = score + 4"
        else:
            sql += ", score = score - 1"
            
        # Add subject-specific increment
        if subject in subj_map:
            att_col, cor_col = subj_map[subject]
            sql += f", {att_col} = {att_col} + 1"
            if is_correct:
                sql += f", {cor_col} = {cor_col} + 1"
        
        conn.execute(f"INSERT OR IGNORE INTO stats (user_id) VALUES ({user_id})")
        conn.execute(f"{sql} WHERE user_id = ?", (user_id,))

def update_group_stats(user_id, chat_id, is_correct):
    """Updates the daily leaderboard data"""
    with get_db() as conn:
        score_inc = 4 if is_correct else -1
        cor_inc = 1 if is_correct else 0
        
        conn.execute("""
            INSERT INTO group_stats (user_id, chat_id, score, correct, attempted) 
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET 
            score = score + ?, correct = correct + ?, attempted = attempted + 1
        """, (user_id, chat_id, score_inc, cor_inc, score_inc, cor_inc))
      
# --- SCORECARD & PROFILE DATA FETCHERS ---
def get_user_scorecard_data(user_id):
    """Fetches all data for the /scorecard and /mystats commands"""
    with get_db() as conn:
        # Get user info
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        
        # Get lifetime stats
        stats = conn.execute("SELECT * FROM stats WHERE user_id = ?", (user_id,)).fetchone()
        
        if not stats:
            return None

        # Calculate Global Rank
        rank_res = conn.execute(
            "SELECT COUNT(*) + 1 as rank FROM stats WHERE score > ?", 
            (stats['score'],)
        ).fetchone()
        
        # Get Group Rank (Daily)
        group_rank = "N/A"
        # Optional: You can add logic here to fetch rank within a specific group if needed

        return {
            "name": user['first_name'] if user else "User",
            "score": stats['score'],
            "total_att": stats['attempted'],
            "total_cor": stats['correct'],
            "bio_att": stats['bio_att'], "bio_cor": stats['bio_cor'],
            "phy_att": stats['phy_att'], "phy_cor": stats['phy_cor'],
            "che_att": stats['che_att'], "che_cor": stats['che_cor'],
            "global_rank": rank_res['rank'],
            "group_rank": group_rank
        }

# --- NIGHTLY REFRESH & SETTINGS ---
def reset_daily_leaderboard():
    """Wipes the group_stats table at 10:15 PM"""
    with get_db() as conn:
        conn.execute("DELETE FROM group_stats")
        # Reset any other daily counters in settings if needed
        conn.execute("UPDATE settings SET value = '0' WHERE key = 'total_sent'")

def set_setting(key, value):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

def get_setting(key, default=None):
    with get_db() as conn:
        res = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return res['value'] if res else default

# --- ADMIN ANALYTICS ---
def update_user_status(user_id, status='active'):
    """Marks user as active or blocked for admin stats"""
    with get_db() as conn:
        conn.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))

def get_admin_bot_stats():
    """Returns data for the /botstats command"""
    with get_db() as conn:
        stats = {}
        stats['total_users'] = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
        stats['direct_users'] = conn.execute("SELECT COUNT(*) as c FROM users WHERE source = 'DM'").fetchone()['c']
        stats['group_users'] = conn.execute("SELECT COUNT(*) as c FROM users WHERE source = 'Group'").fetchone()['c']
        stats['blocked_users'] = conn.execute("SELECT COUNT(*) as c FROM users WHERE status = 'blocked'").fetchone()['c']
        stats['total_groups'] = conn.execute("SELECT COUNT(*) as c FROM chats WHERE type != 'private'").fetchone()['c']
        return stats

async def get_leaderboard_data(chat_id=None, limit=10):
    """Fetches leaderboard data using Async Await."""
    async with get_db() as conn:  # Changed 'with' to 'async with'
        if chat_id:
            # We MUST 'await' the execute call
            res = await conn.execute("""
                SELECT u.first_name, gs.user_id, gs.chat_id, gs.score 
                FROM group_stats gs 
                JOIN users u ON gs.user_id = u.user_id 
                WHERE gs.chat_id = ? ORDER BY gs.score DESC LIMIT ?
            """, (chat_id, limit))
            return res.fetchall()
        
        # Global leaderboard
        res = await conn.execute("""
            SELECT u.first_name, s.user_id, NULL, s.score 
            FROM stats s 
            JOIN users u ON s.user_id = u.user_id 
            ORDER BY s.score DESC LIMIT ?
        """, (limit,))
        return res.fetchall()
        


def delete_all_questions():
    with get_db() as conn:
        conn.execute("DELETE FROM questions")

def delete_all_compliments():
    with get_db() as conn:
        conn.execute("DELETE FROM compliments")
        

# --- USER REGISTRATION ---
def register_user(user_id, username, first_name, source='Group'):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, joined_at, source, status)
            VALUES (?, ?, ?, ?, ?, 'active')
            ON CONFLICT(user_id) DO UPDATE SET 
            username = excluded.username, first_name = excluded.first_name, status = 'active'
        """, (user_id, username, first_name, datetime.now().isoformat(), source))
  
