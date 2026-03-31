#!/usr/bin/env python3
"""
Quick demo for hackathon judges
Shows agent solving easy, medium, and hard scenarios
"""

import requests
import json
import os

BASE_URL = os.getenv("ENV_URL", "http://localhost:7860")  # Or your HF Space URL

def demo_scenario(scenario_id: str, description: str):
    print(f"\n{'='*60}")
    print(f"Scenario: {scenario_id}")
    print(f"{'='*60}")
    
    # Reset
    try:
        r = requests.post(f"{BASE_URL}/reset", json={"scenario_id": scenario_id})
        r.raise_for_status()
        obs = r.json()
    except Exception as e:
        print(f"Failed to reset environment: {e}")
        return
        
    print(f"Difficulty: {obs['difficulty']}")
    print(f"Problem: {description}")
    print(f"\nBroken SQL:\n{obs['broken_sql']}")
    
    if obs.get('hint'):
        print(f"\n💡 Hint: {obs['hint']}")
    
    # Show sample solution (pretend agent fixed it)
    if "easy" in scenario_id:
        fixed = "ALTER TABLE users ADD COLUMN email TEXT DEFAULT '';"
    elif "medium" in scenario_id:
        fixed = "ALTER TABLE customers ADD COLUMN email TEXT NOT NULL DEFAULT 'unknown';"
    else:  # hard
        fixed = "UPDATE user_settings SET theme='auto' WHERE user_id=1;"
    
    print(f"\n✅ Agent Fix:\n{fixed}")
    
    # Submit
    try:
        r = requests.post(f"{BASE_URL}/step", json={
            "fixed_sql": fixed,
            "explanation": "Fixed the issue",
            "confidence": 0.9
        })
        result = r.json()
        
        gr = result['info']['grading_result']
        print(f"\n📊 Score: {gr['total_score']}/100")
        print(f"💰 Reward: {result['reward']:.3f}")
        
        if gr.get('silent_corruption_detected'):
            print("🚨 Silent corruption detected and prevented!")
    except Exception as e:
        print(f"Evaluation failed: {e}")

if __name__ == "__main__":
    print("🛡️ SQL Migration Safety Gym - Judge Demo")
    
    # Easy
    demo_scenario("easy_001_missing_comma", "Missing comma in ALTER TABLE")
    
    # Medium  
    demo_scenario("medium_001_notnull_no_default", "NOT NULL without DEFAULT")
    
    # Hard (the killer feature)
    demo_scenario("hard_001_update_no_where", "UPDATE without WHERE (silent corruption)")
    
    print(f"\n{'='*60}")
    print("Demo complete! Try other scenarios with:")
    print(f"  curl {BASE_URL}/scenarios")
    print(f"{'='*60}")
