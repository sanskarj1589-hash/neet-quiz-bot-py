import os
from datetime import datetime
from pymongo import MongoClient

# Fetch MongoDB URI from Environment Variables
MONGO_URI = os.getenv("MONGO_URI")

# Initialize MongoDB Connection
client = MongoClient(MONGO_URI)
db = client['neetiq_bot_db']

# Collections Mapping
questions = db['questions']
users = db['users']
stats = db['stats']
group_stats = db['group_stats']
settings = db['settings']
active_polls = db['active_polls']

def init_db():
    """Sets up default settings in MongoDB."""
    print("Connecting to MongoDB Atlas...")
    defaults = [
        {'key': 'footer_text', 'value': 'NEETIQBot'},
        {'key': 'footer_enabled', 'value': '1'},
        {'key': 'autoquiz_enabled', 'value': '0'},
        {'key': 'autoquiz_interval', 'value': '30'}
    ]
    for d in defaults:
        settings.update_one({'key': d['key']}, {'$setOnInsert': d}, upsert=True)
    print("🚀 MongoDB connection successful and initialized.")

def update_user_stats(user_id, chat_id, is_correct, username=None, first_name=None):
    """Updates points (+4/-1) and user info."""
    # Sync User Data
    users.update_one(
        {'user_id': user_id},
        {'$set': {'username': username, 'first_name': first_name, 'last_seen': datetime.now()}},
        upsert=True
    )

    score_val = 4 if is_correct else -1
    correct_val = 1 if is_correct else 0

    # Update Global Stats
    stats.update_one(
        {'user_id': user_id},
        {
            '$inc': {'attempted': 1, 'correct': correct_val, 'score': score_val},
            '$set': {'last_date': datetime.now().strftime("%Y-%m-%d")}
        },
        upsert=True
    )

    # Update Group Stats
    if chat_id and chat_id < 0:
        group_stats.update_one(
            {'chat_id': chat_id, 'user_id': user_id},
            {'$inc': {'attempted': 1, 'correct': correct_val, 'score': score_val}},
            upsert=True
        )

def get_leaderboard_data(chat_id=None, limit=25):
    """Returns leaderboard as a list of tuples for neetiq.py compatibility."""
    source = group_stats if chat_id else stats
    match_query = {'chat_id': chat_id} if chat_id else {}
    
    pipeline = [
        {'$match': match_query},
        {'$lookup': {
            'from': 'users', 
            'localField': 'user_id', 
            'foreignField': 'user_id', 
            'as': 'info'
        }},
        {'$sort': {'score': -1}},
        {'$limit': limit}
    ]
    
    docs = list(source.aggregate(pipeline))
    results = []
    for d in docs:
        user_info = d['info'][0] if d.get('info') else {}
        name = f"@{user_info.get('username')}" if user_info.get('username') else user_info.get('first_name', "Unknown")
        results.append((name, d.get('attempted', 0), d.get('correct', 0), d.get('score', 0)))
    return results

def get_setting(key, default=None):
    """Fetches a setting value from the database."""
    doc = settings.find_one({'key': key})
    return doc['value'] if doc else default

if __name__ == "__main__":
    init_db()
    
