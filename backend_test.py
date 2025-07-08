import pytest
import httpx
import json
import time
from datetime import datetime, timedelta
import os

# Get the backend URL from the frontend .env file
BACKEND_URL = "https://386cc050-240b-4776-9840-a773728fe0c4.preview.emergentagent.com"
API_BASE_URL = f"{BACKEND_URL}/api"

# Test data
TEST_USER_EMAIL = f"test_user_{int(time.time())}@example.com"
TEST_USER_NAME = "Test User"
SESSION_ID = None
USER_ID = None

# HTTP client with timeout
http_client = httpx.Client(timeout=10.0)

# Helper functions
def generate_unique_email():
    """Generate a unique email for testing"""
    return f"test_user_{int(time.time())}@example.com"

# Tests
def test_health_endpoint():
    """Test the health endpoint"""
    response = http_client.get(f"{API_BASE_URL}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "DubCheck API"
    print("✅ Health endpoint test passed")

def test_user_registration():
    """Test user registration"""
    global SESSION_ID, USER_ID
    
    # Generate unique email for this test run
    email = generate_unique_email()
    
    payload = {
        "email": email,
        "name": TEST_USER_NAME
    }
    
    print(f"Sending registration request to {API_BASE_URL}/register with payload: {payload}")
    try:
        response = http_client.post(f"{API_BASE_URL}/register", json=payload)
        print(f"Registration response status: {response.status_code}")
        print(f"Registration response body: {response.text}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "session_id" in data
        assert "user" in data
        assert data["user"]["email"] == email
        assert data["user"]["name"] == TEST_USER_NAME
        assert data["user"]["plan"] == "free"
        assert data["user"]["credits"] == 30
        assert "credits_reset_date" in data["user"]
        assert "created_at" in data["user"]
        assert data["user"]["is_active"] is True
        
        # Store session ID for subsequent tests
        SESSION_ID = data["session_id"]
        USER_ID = data["user"]["id"]
        
        print(f"✅ User registration test passed - Created user with email: {email}")
    except Exception as e:
        print(f"Registration test failed with error: {str(e)}")
        raise

def test_duplicate_registration():
    """Test registration with duplicate email"""
    # Try to register with the same email
    payload = {
        "email": TEST_USER_EMAIL,
        "name": TEST_USER_NAME
    }
    
    response = http_client.post(f"{API_BASE_URL}/register", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "already exists" in data["detail"].lower()
    
    print("✅ Duplicate registration test passed")

def test_user_login():
    """Test user login"""
    global SESSION_ID
    
    payload = {
        "email": TEST_USER_EMAIL
    }
    
    response = http_client.post(f"{API_BASE_URL}/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "session_id" in data
    assert "user" in data
    assert data["user"]["email"] == TEST_USER_EMAIL
    
    # Update session ID for subsequent tests
    SESSION_ID = data["session_id"]
    
    print("✅ User login test passed")

def test_login_nonexistent_user():
    """Test login with non-existent user"""
    payload = {
        "email": "nonexistent_user@example.com"
    }
    
    response = http_client.post(f"{API_BASE_URL}/login", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()
    
    print("✅ Non-existent user login test passed")

def test_get_user_profile():
    """Test getting user profile"""
    headers = {
        "Authorization": f"Bearer {SESSION_ID}"
    }
    
    response = http_client.get(f"{API_BASE_URL}/user/profile", headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    # Verify user data
    assert data["email"] == TEST_USER_EMAIL
    assert data["name"] == TEST_USER_NAME
    assert "credits" in data
    assert "plan" in data
    
    print("✅ Get user profile test passed")

def test_invalid_session():
    """Test using an invalid session ID"""
    headers = {
        "Authorization": "Bearer invalid_session_id"
    }
    
    response = http_client.get(f"{API_BASE_URL}/user/profile", headers=headers)
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "invalid session" in data["detail"].lower()
    
    print("✅ Invalid session test passed")

def test_get_plans():
    """Test getting available plans"""
    response = http_client.get(f"{API_BASE_URL}/plans")
    assert response.status_code == 200
    data = response.json()
    
    # Verify plans data
    assert "free" in data
    assert "pro" in data
    assert "premium" in data
    assert "family_pro" in data
    assert "family_premium" in data
    
    # Verify plan structure
    free_plan = data["free"]
    assert free_plan["plan_name"] == "free"
    assert free_plan["weekly_credits"] == 30
    assert free_plan["priority_processing"] is False
    assert free_plan["video_analysis"] is False
    assert free_plan["max_family_members"] == 1
    
    print("✅ Get plans test passed")

def test_fact_check_short_text():
    """Test fact-checking with short text (≤50 words)"""
    headers = {
        "Authorization": f"Bearer {SESSION_ID}"
    }
    
    short_text = "The Earth is round and orbits the Sun."
    
    payload = {
        "text": short_text,
        "priority": False
    }
    
    response = http_client.post(f"{API_BASE_URL}/fact-check", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "id" in data
    assert data["text"] == short_text
    assert "likelihood_score" in data
    assert "reasoning" in data
    assert "sources" in data
    assert "credits_used" in data
    assert data["credits_used"] == 1  # Short text should use 1 credit
    assert "created_at" in data
    
    print("✅ Fact check short text test passed")

def test_fact_check_medium_text():
    """Test fact-checking with medium text (51-200 words)"""
    headers = {
        "Authorization": f"Bearer {SESSION_ID}"
    }
    
    # Generate medium text (51-200 words)
    medium_text = "The Earth is the third planet from the Sun and the only astronomical object known to harbor life. " * 10
    
    payload = {
        "text": medium_text,
        "priority": False
    }
    
    response = http_client.post(f"{API_BASE_URL}/fact-check", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    # Verify credits used
    assert data["credits_used"] == 2  # Medium text should use 2 credits
    
    print("✅ Fact check medium text test passed")

def test_fact_check_long_text():
    """Test fact-checking with long text (201-500 words)"""
    headers = {
        "Authorization": f"Bearer {SESSION_ID}"
    }
    
    # Generate long text (201-500 words)
    long_text = "The Earth is the third planet from the Sun and the only astronomical object known to harbor life. " * 25
    
    payload = {
        "text": long_text,
        "priority": False
    }
    
    response = http_client.post(f"{API_BASE_URL}/fact-check", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    # Verify credits used
    assert data["credits_used"] == 3  # Long text should use 3 credits
    
    print("✅ Fact check long text test passed")

def test_fact_check_very_long_text():
    """Test fact-checking with very long text (>500 words)"""
    headers = {
        "Authorization": f"Bearer {SESSION_ID}"
    }
    
    # Generate very long text (>500 words)
    very_long_text = "The Earth is the third planet from the Sun and the only astronomical object known to harbor life. " * 60
    
    payload = {
        "text": very_long_text,
        "priority": False
    }
    
    response = http_client.post(f"{API_BASE_URL}/fact-check", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    # Verify credits used
    assert data["credits_used"] == 5  # Very long text should use 5 credits
    
    print("✅ Fact check very long text test passed")

def test_get_fact_check_history():
    """Test getting fact-check history"""
    headers = {
        "Authorization": f"Bearer {SESSION_ID}"
    }
    
    response = http_client.get(f"{API_BASE_URL}/user/fact-checks", headers=headers)
    assert response.status_code == 200
    data = response.json()
    
    # Verify it's a list
    assert isinstance(data, list)
    
    # We should have at least the fact checks we just created
    assert len(data) >= 3
    
    # Verify structure of first item
    if data:
        first_check = data[0]
        assert "id" in first_check
        assert "text" in first_check
        assert "likelihood_score" in first_check
        assert "reasoning" in first_check
        assert "sources" in first_check
        assert "credits_used" in first_check
        assert "created_at" in first_check
    
    print("✅ Get fact check history test passed")

def test_insufficient_credits():
    """Test fact-checking with insufficient credits"""
    # First, let's use up all credits
    headers = {
        "Authorization": f"Bearer {SESSION_ID}"
    }
    
    # Get current user profile to check credits
    response = http_client.get(f"{API_BASE_URL}/user/profile", headers=headers)
    data = response.json()
    current_credits = data["credits"]
    print(f"Current credits: {current_credits}")
    
    # Use up all credits with a series of requests
    very_long_text = "The Earth is the third planet from the Sun and the only astronomical object known to harbor life. " * 60
    
    # Calculate how many requests we need to use up credits
    requests_needed = (current_credits // 5) + 1  # Add 1 to ensure we use all credits
    
    print(f"Making {requests_needed} requests to use up credits")
    for i in range(requests_needed):
        payload = {
            "text": very_long_text,
            "priority": False
        }
        try:
            response = http_client.post(f"{API_BASE_URL}/fact-check", json=payload, headers=headers)
            print(f"Request {i+1}: Status {response.status_code}")
            
            # If we've already run out of credits, we can stop
            if response.status_code == 402:
                print("Already out of credits, stopping")
                break
        except Exception as e:
            print(f"Error in request {i+1}: {str(e)}")
    
    # Now try with a small request that should fail
    payload = {
        "text": "This is a test.",
        "priority": False
    }
    
    response = http_client.post(f"{API_BASE_URL}/fact-check", json=payload, headers=headers)
    print(f"Final test request status: {response.status_code}")
    
    # We expect a 402 Payment Required (insufficient credits)
    assert response.status_code == 402
    data = response.json()
    assert "detail" in data
    assert "insufficient credits" in data["detail"].lower()
    
    print("✅ Insufficient credits test passed")

def run_all_tests():
    """Run all tests in sequence"""
    print("\n🔍 Starting DubCheck Backend API Tests\n")
    
    # Initialize with a test user
    global TEST_USER_EMAIL
    TEST_USER_EMAIL = generate_unique_email()
    
    tests_passed = 0
    tests_failed = 0
    
    # Define all tests
    tests = [
        test_health_endpoint,
        test_user_registration,
        test_duplicate_registration,
        test_user_login,
        test_login_nonexistent_user,
        test_get_user_profile,
        test_invalid_session,
        test_get_plans,
        test_fact_check_short_text,
        test_fact_check_medium_text,
        test_fact_check_long_text,
        test_fact_check_very_long_text,
        test_get_fact_check_history,
        test_insufficient_credits
    ]
    
    # Run each test individually
    for test_func in tests:
        try:
            test_func()
            tests_passed += 1
        except Exception as e:
            tests_failed += 1
            print(f"\n❌ Test {test_func.__name__} failed: {str(e)}\n")
    
    print(f"\n✅ Tests completed: {tests_passed} passed, {tests_failed} failed\n")
    return tests_failed == 0

if __name__ == "__main__":
    try:
        run_all_tests()
    except Exception as e:
        import traceback
        print(f"\n❌ Test failed with exception: {str(e)}")
        print("\nTraceback:")
        traceback.print_exc()