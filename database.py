import os
from datetime import datetime
from pymongo import MongoClient

# Fetch Environment Variables from Render
MONGO_URI = os.getenv("MONGO_URI")

# Initialize MongoDB
# Note: MongoDB handles connection pooling, so no 'with get_db()' is needed
client = MongoClient(MONGO_URI)
db = client['neetiq_bot_db']

# Collections
questions = db['questions']
users = db['users']
stats = db['stats']
group_stats = db['group_stats']
settings = db['settings']
active_polls = db['active_polls']

def init_db():
    """Initializes collections and default settings."""
    print("Connecting to MongoDB Atlas...")
    defaults = [
        {'key': 'footer_text', 'value': 'NEETIQBot'},
        {'key': 'footer_enabled', 'value': '1'},
        {'key': 'autoquiz_enabled', 'value': '0'},
        {'key': 'autoquiz_interval', 'value': '30'}
    ]
    for d in defaults:
        settings.update_one({'key': d['key']}, {'$setOnInsert': d}, upsert=True)
    
    # Create indexes for performance
    stats.create_index("user_id", unique=True)
    group_stats.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
    print("🚀 MongoDB Initialized Successfully.")

def update_user_stats(user_id, chat_id, is_correct, username=None, first_name=None):
    """Updates global and group points (+4 for correct, -1 for wrong)."""
    # Sync User Profile
    users.update_one(
        {'user_id': user_id},
        {'$set': {'username': username, 'first_name': first_name, 'last_seen': datetime.now()}},
        upsert=True
    )

    point_change = 4 if is_correct else -1
    correct_inc = 1 if is_correct else 0

    # Update Global Stats
    stats.update_one(
        {'user_id': user_id},
        {
            '$inc': {'attempted': 1, 'correct': correct_inc, 'score': point_change},
            '$set': {'last_date': datetime.now().strftime("%Y-%m-%d")}
        },
        upsert=True
    )

    # Update Group Stats
    if chat_id and chat_id < 0:
        group_stats.update_one(
            {'chat_id': chat_id, 'user_id': user_id},
            {'$inc': {'attempted': 1, 'correct': correct_inc, 'score': point_change}},
            upsert=True
        )

def get_leaderboard_data(chat_id=None, limit=25):
    """Returns leaderboard as tuples (Name, Attempted, Correct, Score) for main file compatibility."""
    source_coll = group_stats if chat_id else stats
    match_filter = {'chat_id': chat_id} if chat_id else {}

    pipeline = [
        {'$match': match_filter},
        {'$lookup': {
            'from': 'users', 
            'localField': 'user_id', 
            'foreignField': 'user_id', 
            'as': 'u'
        }},
        {'$sort': {'score': -1}},
        {'$limit': limit}
    ]

    docs = list(source_coll.aggregate(pipeline))
    results = []
    for d in docs:
        u_info = d['u'][0] if d.get('u') else {}
        name = f"@{u_info.get('username')}" if u_info.get('username') else u_info.get('first_name', f"User {d['user_id']}")
        results.append((name, d.get('attempted', 0), d.get('correct', 0), d.get('score', 0)))
    return results

def get_setting(key, default=None):
    """Helper to fetch settings like footer_text."""
    doc = settings.find_one({'key': key})
    return doc['value'] if doc else default

if __name__ == "__main__":
    init_db()
      
