from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict
import os
from pymongo import MongoClient
import uuid
from datetime import datetime, timedelta
import httpx
import asyncio
from emergentintegrations.llm.chat import LlmChat, UserMessage
import json

app = FastAPI(title="DubCheck API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# MongoDB setup
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "dubcheck_database")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

# Collections
users_collection = db.users
sessions_collection = db.sessions
fact_checks_collection = db.fact_checks
credits_collection = db.credits

# Models
class User(BaseModel):
    id: str
    email: str
    name: str
    plan: str = "free"  # free, pro, premium, family_pro, family_premium
    credits: int = 30
    credits_reset_date: datetime
    created_at: datetime
    is_active: bool = True

class FactCheckRequest(BaseModel):
    text: str
    priority: bool = False

class FactCheckResponse(BaseModel):
    id: str
    text: str
    likelihood_score: float
    reasoning: str
    sources: List[Dict]
    credits_used: int
    created_at: datetime

class CreditPlan(BaseModel):
    plan_name: str
    weekly_credits: int
    priority_processing: bool
    video_analysis: bool
    max_family_members: int

# Plan configurations
PLANS = {
    "free": CreditPlan(
        plan_name="free",
        weekly_credits=30,
        priority_processing=False,
        video_analysis=False,
        max_family_members=1
    ),
    "pro": CreditPlan(
        plan_name="pro",
        weekly_credits=100,
        priority_processing=True,
        video_analysis=False,
        max_family_members=1
    ),
    "premium": CreditPlan(
        plan_name="premium",
        weekly_credits=500,
        priority_processing=True,
        video_analysis=True,
        max_family_members=1
    ),
    "family_pro": CreditPlan(
        plan_name="family_pro",
        weekly_credits=100,
        priority_processing=True,
        video_analysis=False,
        max_family_members=3
    ),
    "family_premium": CreditPlan(
        plan_name="family_premium",
        weekly_credits=500,
        priority_processing=True,
        video_analysis=True,
        max_family_members=5
    )
}

# Helper functions
def calculate_credits_needed(text: str) -> int:
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

def get_user_from_session(session_id: str) -> Optional[Dict]:
    """Get user from session"""
    session = sessions_collection.find_one({"session_id": session_id})
    if not session:
        return None
    
    user = users_collection.find_one({"id": session["user_id"]})
    return user

def reset_weekly_credits(user_id: str):
    """Reset weekly credits for user"""
    user = users_collection.find_one({"id": user_id})
    if not user:
        return
    
    plan = PLANS.get(user["plan"], PLANS["free"])
    users_collection.update_one(
        {"id": user_id},
        {
            "$set": {
                "credits": plan.weekly_credits,
                "credits_reset_date": datetime.utcnow() + timedelta(days=7)
            }
        }
    )

async def search_web(query: str) -> List[Dict]:
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
        async with httpx.AsyncClient() as client:
            response = await client.post(
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

async def fact_check_with_ai(text: str, sources: List[Dict]) -> Dict:
    """Fact-check text using OpenAI GPT-4O"""
    if not OPENAI_API_KEY:
        return {
            "likelihood_score": 0.5,
            "reasoning": "AI fact-checking unavailable - API key not configured"
        }
    
    # Prepare sources context
    sources_context = "\n\n".join([
        f"Source {i+1}: {source['title']}\nURL: {source['url']}\nContent: {source['snippet']}"
        for i, source in enumerate(sources[:3])  # Use top 3 sources
    ])
    
    system_message = """You are a professional fact-checker. Analyze the given text against the provided sources and determine how likely it is to be true. 

Provide:
1. A likelihood score from 0.0 to 1.0 (0.0 = definitely false, 1.0 = definitely true)
2. Clear reasoning explaining your assessment
3. Reference specific sources when possible

Be objective and balanced in your analysis."""
    
    user_message_text = f"""
Text to fact-check: "{text}"

Available sources:
{sources_context}

Please provide a JSON response with:
- "likelihood_score": float between 0.0 and 1.0
- "reasoning": detailed explanation of your assessment
"""
    
    try:
        chat = LlmChat(
            api_key=OPENAI_API_KEY,
            session_id=f"fact_check_{uuid.uuid4()}",
            system_message=system_message
        ).with_model("openai", "gpt-4o").with_max_tokens(1000)
        
        user_message = UserMessage(text=user_message_text)
        response = await chat.send_message(user_message)
        
        # Try to parse JSON response
        try:
            result = json.loads(response)
            return {
                "likelihood_score": float(result.get("likelihood_score", 0.5)),
                "reasoning": result.get("reasoning", "Analysis completed")
            }
        except json.JSONDecodeError:
            # Fallback parsing
            lines = response.split('\n')
            likelihood_score = 0.5
            reasoning = response
            
            for line in lines:
                if "likelihood_score" in line.lower():
                    try:
                        score_str = line.split(':')[1].strip().replace(',', '')
                        likelihood_score = float(score_str)
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

# Routes
@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "DubCheck API"}

@app.post("/api/register")
async def register_user(request: Request):
    """Register new user"""
    body = await request.json()
    email = body.get("email")
    name = body.get("name")
    
    if not email or not name:
        raise HTTPException(status_code=400, detail="Email and name required")
    
    # Check if user exists
    existing_user = users_collection.find_one({"email": email})
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
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
    
    return {"session_id": session_id, "user": user}

@app.post("/api/login")
async def login_user(request: Request):
    """Login user"""
    body = await request.json()
    email = body.get("email")
    
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    
    user = users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Create session
    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "user_id": user["id"],
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=7)
    }
    
    sessions_collection.insert_one(session)
    
    return {"session_id": session_id, "user": user}

@app.post("/api/fact-check")
async def fact_check_text(request: FactCheckRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Fact-check text"""
    session_id = credentials.credentials
    user = get_user_from_session(session_id)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    # Check if credits need reset
    if datetime.utcnow() > user["credits_reset_date"]:
        reset_weekly_credits(user["id"])
        user = users_collection.find_one({"id": user["id"]})
    
    # Calculate credits needed
    credits_needed = calculate_credits_needed(request.text)
    
    if user["credits"] < credits_needed:
        raise HTTPException(status_code=402, detail="Insufficient credits")
    
    # Perform web search
    search_query = f"fact check verify: {request.text[:100]}"
    sources = await search_web(search_query)
    
    # Perform AI fact-checking
    ai_result = await fact_check_with_ai(request.text, sources)
    
    # Create fact-check record
    fact_check_id = str(uuid.uuid4())
    fact_check = {
        "id": fact_check_id,
        "user_id": user["id"],
        "text": request.text,
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
    
    return FactCheckResponse(**fact_check)

@app.get("/api/user/profile")
async def get_user_profile(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get user profile"""
    session_id = credentials.credentials
    user = get_user_from_session(session_id)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    return user

@app.get("/api/user/fact-checks")
async def get_user_fact_checks(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get user's fact-check history"""
    session_id = credentials.credentials
    user = get_user_from_session(session_id)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    fact_checks = list(fact_checks_collection.find(
        {"user_id": user["id"]},
        {"_id": 0}
    ).sort("created_at", -1).limit(20))
    
    return fact_checks

@app.get("/api/plans")
async def get_plans():
    """Get available plans"""
    return PLANS

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)