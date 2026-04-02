"""
Reference client for SQL Migration Safety Gym (OpenEnv RFC 001/002)
This script demonstrates how an external agent communicates with the 
environment over HTTP.
"""

import requests
import json
import os

def run_demo_episode():
    # Use ENV_URL if set, otherwise default to local development port 7860
    BASE_URL = os.environ.get("ENV_URL", "http://localhost:7860")
    
    print(f"🚀 Connecting to SQL Migration Safety Gym at {BASE_URL}...")
    
    # 1. RESET: Initialize a deterministic benchmark task
    # Standard OpenEnv reset expects 'task_id' (easy/medium/hard)
    try:
        print("\n[Step 1] Resetting environment to 'hard' benchmark...")
        resp = requests.post(f"{BASE_URL}/reset", json={"task_id": "hard"}, timeout=10)
        resp.raise_for_status()
        obs = resp.json()
        
        print(f"✅ Reset successful. Scenario: {obs['scenario_id']}")
        print(f"📝 Description: {obs['description']}")
        print(f"💡 Hint: {obs['hint'] or 'None (HARD mode active)'}")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("Is the server running? 'uvicorn app.main:app --port 7860'")
        return

    # 2. STEP: Agent proposes a migration fix
    # This is an 'Expert' fix that avoids sequential-execution corruption
    expert_fix = """
    BEGIN TRANSACTION;
    -- Step 1: Add all required columns first
    ALTER TABLE orders ADD COLUMN discount_pct REAL DEFAULT 0.0;
    ALTER TABLE orders ADD COLUMN final_amount REAL DEFAULT 0.0;

    -- Step 2: Populate data after schema is stable
    UPDATE orders 
        SET discount_pct = total_amount * 0.10 
        WHERE customer_tier = 'premium';
        
    UPDATE orders 
        SET final_amount = total_amount * (1.0 - discount_pct);
    COMMIT;
    """
    
    print("\n[Step 2] Executing expert migration fix...")
    step_resp = requests.post(f"{BASE_URL}/step", json={
        "fixed_sql": expert_fix,
        "explanation": "Applied transactional reordering to prevent silent corruption.",
        "confidence": 1.0
    })
    
    if step_resp.status_code == 200:
        result = step_resp.json()
        reward = result['reward']
        grading = result['info']['grading_result']
        
        print(f"📊 Episode Result: Reward {reward}")
        print(f"⭐ Data Integrity: {grading['data_integrity_score']}/45")
        print(f"⭐ Schema Score: {grading['schema_correct_score']}/35")
        print(f"💬 Feedback: {grading['detailed_feedback']}")
    else:
        print(f"❌ Step failed: {step_resp.text}")

if __name__ == "__main__":
    run_demo_episode()
