from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from pymongo import MongoClient
from bson.objectid import ObjectId
import uuid
from datetime import datetime, timedelta
import requests
import json
from openai import OpenAI
import time

app = Flask(__name__)
CORS(app)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Configuration
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "dubcheck_database")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# MongoDB setup
client = MongoClient(MONGO_URL)
db = client[DB_NAME]

# Collections
users_collection = db.users
sessions_collection = db.sessions
fact_checks_collection = db.fact_checks

# OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Plan configurations
PLANS = {
    "free": {
        "plan_name": "free",
        "weekly_credits": 30,
        "priority_processing": False,
        "video_analysis": False,
        "max_family_members": 1
    },
    "pro": {
        "plan_name": "pro",
        "weekly_credits": 100,
        "priority_processing": True,
        "video_analysis": False,
        "max_family_members": 1
    },
    "premium": {
        "plan_name": "premium",
        "weekly_credits": 500,
        "priority_processing": True,
        "video_analysis": True,
        "max_family_members": 1
    },
    "family_pro": {
        "plan_name": "family_pro",
        "weekly_credits": 100,
        "priority_processing": True,
        "video_analysis": False,
        "max_family_members": 3
    },
    "family_premium": {
        "plan_name": "family_premium",
        "weekly_credits": 500,
        "priority_processing": True,
        "video_analysis": True,
        "max_family_members": 5
    }
}

# Helper functions
def calculate_credits_needed(text):
    """Calculate credits needed based on text length"""
    word_count = len(text.split())
    if word_count <= 50:
        return 1
    elif word_count <= 200:
        return 2
    elif word_count <= 500:
        return 3
    else:
        return 5

def get_user_from_session(session_id):
    """Get user from session"""
    try:
        session = sessions_collection.find_one({"session_id": session_id})
        if not session:
            return None
        
        # Check if session is expired
        if datetime.utcnow() > session.get("expires_at", datetime.utcnow()):
            return None
        
        user = users_collection.find_one({"id": session["user_id"]})
        return user
    except Exception as e:
        print(f"Error getting user from session: {e}")
        return None

def reset_weekly_credits(user_id):
    """Reset weekly credits for user"""
    try:
        user = users_collection.find_one({"id": user_id})
        if not user:
            return
        
        plan = PLANS.get(user["plan"], PLANS["free"])
        users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "credits": plan["weekly_credits"],
                    "credits_reset_date": datetime.utcnow() + timedelta(days=7)
                }
            }
        )
    except Exception as e:
        print(f"Error resetting credits: {e}")

def search_web(query):
    """Search web using Serper API"""
    if not SERPER_API_KEY:
        return []
    
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "q": query,
        "num": 5
    }
    
    try:
        response = requests.post(
            "https://google.serper.dev/search",
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            sources = []
            
            for result in data.get("organic", []):
                sources.append({
                    "title": result.get("title", ""),
                    "url": result.get("link", ""),
                    "snippet": result.get("snippet", "")
                })
            
            return sources
    except Exception as e:
        print(f"Web search error: {e}")
        return []

def fact_check_with_ai(text, sources):
    """Fact-check text using OpenAI GPT-4O"""
    if not openai_client:
        return {
            "likelihood_score": 0.5,
            "reasoning": "AI fact-checking unavailable - OpenAI API key not configured"
        }
    
    # Prepare sources context
    sources_context = "\n\n".join([
        f"Source {i+1}: {source['title']}\nURL: {source['url']}\nContent: {source['snippet']}"
        for i, source in enumerate(sources[:3])  # Use top 3 sources
    ])
    
    system_message = """You are a professional fact-checker. Analyze the given text against the provided sources and determine how likely it is to be true. 

Provide your response as a JSON object with:
1. "likelihood_score": A number from 0.0 to 1.0 (0.0 = definitely false, 1.0 = definitely true)
2. "reasoning": Clear explanation of your assessment

Be objective and balanced in your analysis."""
    
    user_message = f"""
Text to fact-check: "{text}"

Available sources:
{sources_context}

Please provide a JSON response with:
- "likelihood_score": float between 0.0 and 1.0
- "reasoning": detailed explanation of your assessment
"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        
        ai_response = response.choices[0].message.content
        
        # Try to parse JSON response
        try:
            result = json.loads(ai_response)
            return {
                "likelihood_score": float(result.get("likelihood_score", 0.5)),
                "reasoning": result.get("reasoning", "Analysis completed")
            }
        except json.JSONDecodeError:
            # Fallback parsing
            likelihood_score = 0.5
            reasoning = ai_response
            
            # Try to extract likelihood score from text
            lines = ai_response.split('\n')
            for line in lines:
                if "likelihood_score" in line.lower():
                    try:
                        score_str = line.split(':')[1].strip().replace(',', '').replace('"', '')
                        likelihood_score = float(score_str)
                        break
                    except:
                        pass
            
            return {
                "likelihood_score": likelihood_score,
                "reasoning": reasoning
            }
            
    except Exception as e:
        return {
            "likelihood_score": 0.5,
            "reasoning": f"Error during AI analysis: {str(e)}"
        }

def serialize_doc(doc):
    """Convert MongoDB document to JSON serializable format"""
    if doc is None:
        return None
    
    if isinstance(doc, list):
        return [serialize_doc(item) for item in doc]
    
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if key == "_id":
                continue  # Skip MongoDB _id field
            elif isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = serialize_doc(value)
            elif isinstance(value, list):
                result[key] = serialize_doc(value)
            else:
                result[key] = value
        return result
    
    return doc

# Routes
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "DubCheck API"})

@app.route('/api/register', methods=['POST'])
def register_user():
    """Register new user"""
    try:
        data = request.get_json()
        email = data.get("email")
        name = data.get("name")
        
        if not email or not name:
            return jsonify({"error": "Email and name required"}), 400
        
        # Check if user exists
        existing_user = users_collection.find_one({"email": email})
        if existing_user:
            return jsonify({"error": "User already exists"}), 400
        
        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "email": email,
            "name": name,
            "plan": "free",
            "credits": 30,
            "credits_reset_date": datetime.utcnow() + timedelta(days=7),
            "created_at": datetime.utcnow(),
            "is_active": True
        }
        
        users_collection.insert_one(user)
        
        # Create session
        session_id = str(uuid.uuid4())
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=7)
        }
        
        sessions_collection.insert_one(session)
        
        return jsonify({"session_id": session_id, "user": serialize_doc(user)})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login_user():
    """Login user"""
    try:
        data = request.get_json()
        email = data.get("email")
        
        if not email:
            return jsonify({"error": "Email required"}), 400
        
        user = users_collection.find_one({"email": email})
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Create session
        session_id = str(uuid.uuid4())
        session = {
            "session_id": session_id,
            "user_id": user["id"],
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(days=7)
        }
        
        sessions_collection.insert_one(session)
        
        return jsonify({"session_id": session_id, "user": serialize_doc(user)})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/fact-check', methods=['POST'])
def fact_check_text():
    """Fact-check text"""
    try:
        # Get session from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        
        session_id = auth_header.split(' ')[1]
        user = get_user_from_session(session_id)
        
        if not user:
            return jsonify({"error": "Invalid session"}), 401
        
        data = request.get_json()
        text = data.get("text")
        
        if not text:
            return jsonify({"error": "Text required"}), 400
        
        # Check if credits need reset
        if datetime.utcnow() > user.get("credits_reset_date", datetime.utcnow()):
            reset_weekly_credits(user["id"])
            user = users_collection.find_one({"id": user["id"]})
        
        # Calculate credits needed
        credits_needed = calculate_credits_needed(text)
        
        if user["credits"] < credits_needed:
            return jsonify({"error": "Insufficient credits"}), 402
        
        # Perform web search
        search_query = f"fact check verify: {text[:100]}"
        sources = search_web(search_query)
        
        # Perform AI fact-checking
        ai_result = fact_check_with_ai(text, sources)
        
        # Create fact-check record
        fact_check_id = str(uuid.uuid4())
        fact_check = {
            "id": fact_check_id,
            "user_id": user["id"],
            "text": text,
            "likelihood_score": ai_result["likelihood_score"],
            "reasoning": ai_result["reasoning"],
            "sources": sources,
            "credits_used": credits_needed,
            "created_at": datetime.utcnow()
        }
        
        fact_checks_collection.insert_one(fact_check)
        
        # Deduct credits
        users_collection.update_one(
            {"id": user["id"]},
            {"$inc": {"credits": -credits_needed}}
        )
        
        return jsonify(serialize_doc(fact_check))
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/user/profile', methods=['GET'])
def get_user_profile():
    """Get user profile"""
    try:
        # Get session from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        
        session_id = auth_header.split(' ')[1]
        user = get_user_from_session(session_id)
        
        if not user:
            return jsonify({"error": "Invalid session"}), 401
        
        return jsonify(serialize_doc(user))
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/user/fact-checks', methods=['GET'])
def get_user_fact_checks():
    """Get user's fact-check history"""
    try:
        # Get session from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        
        session_id = auth_header.split(' ')[1]
        user = get_user_from_session(session_id)
        
        if not user:
            return jsonify({"error": "Invalid session"}), 401
        
        fact_checks = list(fact_checks_collection.find(
            {"user_id": user["id"]}
        ).sort("created_at", -1).limit(20))
        
        return jsonify(serialize_doc(fact_checks))
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/plans', methods=['GET'])
def get_plans():
    """Get available plans"""
    return jsonify(PLANS)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8001, debug=True)