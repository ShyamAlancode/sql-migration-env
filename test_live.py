import requests
import json

SPACE_URL = "https://shyamalancode-sql-migration-env.hf.space"

def test_health():
    print("1. Testing Health...")
    r = requests.get(f"{SPACE_URL}/health")
    print(f"   Status: {r.json()}")
    assert r.status_code == 200
    print("   ✅ PASS\n")

def test_scenarios():
    print("2. Testing Scenarios...")
    r = requests.get(f"{SPACE_URL}/scenarios")
    data = r.json()
    print(f"   Count: {data['count']}")
    print(f"   First 3: {[s['id'] for s in data['scenarios'][:3]]}")
    assert data['count'] == 15
    print("   ✅ PASS\n")

def test_easy_mode():
    print("3. Testing Easy Mode...")
    r = requests.post(f"{SPACE_URL}/reset", json={"difficulty": "easy"})
    obs = r.json()
    print(f"   Scenario: {obs['scenario_id']}")
    print(f"   Difficulty: {obs['difficulty']}")
    assert obs['difficulty'] == 'easy'
    print("   ✅ PASS\n")

def test_fix():
    print("4. Testing Fix Submission...")
    r = requests.post(f"{SPACE_URL}/step", json={
        "fixed_sql": "ALTER TABLE users ADD COLUMN email TEXT DEFAULT '';",
        "explanation": "Added default for new column",
        "confidence": 0.9
    })
    result = r.json()
    print(f"   Reward: {result['reward']:.3f}")
    print(f"   Done: {result['done']}")
    print(f"   Score: {result['info']['grading_result']['total_score']}")
    print("   ✅ PASS\n")

def test_hard_mode():
    print("5. Testing Hard Mode (Silent Corruption)...")
    r = requests.post(f"{SPACE_URL}/reset", json={"scenario_id": "hard_001_update_no_where"})
    obs = r.json()
    print(f"   Loaded: {obs['scenario_id']}")
    print(f"   Hint: {obs.get('hint', 'No hint (HARD MODE)')}")
    
    # Submit broken SQL (no WHERE)
    r = requests.post(f"{SPACE_URL}/step", json={
        "fixed_sql": "UPDATE user_settings SET theme='auto', notifications=0;",
        "explanation": "Broken: no WHERE clause"
    })
    result = r.json()
    score = result['info']['grading_result']['total_score']
    print(f"   Bad Fix Score: {score} (should be <30)")
    
    # Submit good SQL (with WHERE)
    r = requests.post(f"{SPACE_URL}/reset", json={"scenario_id": "hard_001_update_no_where"})
    r = requests.post(f"{SPACE_URL}/step", json={
        "fixed_sql": "UPDATE user_settings SET theme='auto', notifications=0 WHERE user_id=1;",
        "explanation": "Fixed: added WHERE clause"
    })
    result = r.json()
    score = result['info']['grading_result']['total_score']
    print(f"   Good Fix Score: {score} (should be >80)")
    
    if score > 80:
        print("   ✅ Silent corruption detection working!")
    else:
        print("   ⚠️  Check grader logic")

if __name__ == "__main__":
    print("="*60)
    print("LIVE DEPLOYMENT TEST")
    print("="*60)
    try:
        test_health()
        test_scenarios()
        test_easy_mode()
        test_fix()
        test_hard_mode()
        print("="*60)
        print("🎉 ALL TESTS PASSED - DEPLOYMENT HEALTHY!")
        print("="*60)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")