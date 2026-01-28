import os
import random
from datetime import datetime
from pymongo import MongoClient, UpdateOne

# Read from Render Environment Variables
MONGO_URI = os.getenv("MONGO_URI")

# Initialize Client
client = MongoClient(MONGO_URI)
db = client['neetiq_database']

# Collections (Equivalent to Tables)
questions = db['questions']
users = db['users']
stats = db['stats']
group_stats = db['group_stats']
settings = db['settings']
active_polls = db['active_polls']
compliments = db['compliments']

def init_db():
    """Initializes collections and default settings."""
    print("Connecting to MongoDB Atlas...")
    
    # Default Bot Settings
    defaults = [
        {'key': 'footer_text', 'value': 'NEETIQBot'},
        {'key': 'footer_enabled', 'value': '1'},
        {'key': 'autoquiz_enabled', 'value': '0'},
        {'key': 'autoquiz_interval', 'value': '30'},
        {'key': 'compliments_enabled', 'value': '1'}
    ]
    
    for d in defaults:
        settings.update_one({'key': d['key']}, {'$setOnInsert': d}, upsert=True)
    
    # Ensure indexes for speed
    stats.create_index("user_id", unique=True)
    users.create_index("user_id", unique=True)
    group_stats.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
    
    print("🚀 MongoDB Initialized and Indexed.")
  def update_user_stats(user_id, chat_id, is_correct, username=None, first_name=None):
    """Updates points for both Global and Group leaderboards."""
    
    # 1. Sync User Metadata
    users.update_one(
        {'user_id': user_id},
        {'$set': {
            'username': username, 
            'first_name': first_name, 
            'last_active': datetime.now()
        }},
        upsert=True
    )

    # 2. Scoring Logic
    score_inc = 4 if is_correct else -1
    correct_inc = 1 if is_correct else 0

    # 3. Update Global Stats
    stats.update_one(
        {'user_id': user_id},
        {
            '$inc': {'attempted': 1, 'correct': correct_inc, 'score': score_inc},
            '$set': {'last_date': datetime.now().strftime("%Y-%m-%d")}
        },
        upsert=True
    )

    # 4. Update Group-Specific Stats
    if chat_id < 0:
        group_stats.update_one(
            {'chat_id': chat_id, 'user_id': user_id},
            {'$inc': {'attempted': 1, 'correct': correct_inc, 'score': score_inc}},
            upsert=True
        )

def get_compliment():
    """Fetches a random compliment from the collection."""
    count = compliments.count_documents({})
    if count == 0:
        return "Excellent work!"
    res = compliments.aggregate([{ '$sample': { 'size': 1 } }])
    return list(res)[0]['text']
def get_leaderboard_data(chat_id=None, limit=25):
    """Fetches top players and formats them as tuples (Name, Attempt, Correct, Score)."""
    
    pipeline = []
    if chat_id:
        # Group Leaderboard
        pipeline.append({'$match': {'chat_id': chat_id}})
        source_coll = group_stats
    else:
        # Global Leaderboard
        source_coll = stats
    
    pipeline.extend([
        {'$lookup': {
            'from': 'users',
            'localField': 'user_id',
            'foreignField': 'user_id',
            'as': 'user_info'
        }},
        {'$sort': {'score': -1}},
        {'$limit': limit}
    ])
    
    results = list(source_coll.aggregate(pipeline))
    
    formatted = []
    for r in results:
        u_list = r.get('user_info', [])
        u = u_list[0] if u_list else {}
        
        # Name resolution: Username > First Name > ID
        name = f"@{u.get('username')}" if u.get('username') else u.get('first_name', f"User {r['user_id']}")
        
        formatted.append((
            name, 
            r.get('attempted', 0), 
            r.get('correct', 0), 
            r.get('score', 0)
        ))
    return formatted

# For main.py compatibility (Simple Fetchers)
def get_setting(key, default=None):
    res = settings.find_one({'key': key})
    return res['value'] if res else default

if __name__ == "__main__":
    init_db()
  
