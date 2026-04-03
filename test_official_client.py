# test_official_client.py
# Tests if your env works with the official OpenEnv client pattern
# Uses X-Session-ID header so reset and step share the same session.

import requests
import json

BASE_URL = "http://localhost:7860"

# Test 1: Health check structure
print("=" * 60)
print("TEST 1: Health Check")
health = requests.get(f"{BASE_URL}/health").json()
print("Response:", json.dumps(health, indent=2))
assert "status" in health, "FAIL: missing status field"
assert health["scenarios_available"] == 24, f"FAIL: expected 24 scenarios, got {health['scenarios_available']}"
print("PASS: health check — 24 scenarios available\n")

# Test 2: Reset structure
print("=" * 60)
print("TEST 2: Reset Response Structure")
r = requests.post(f"{BASE_URL}/reset", json={"task_id": "easy"})
session_id = r.headers.get("X-Session-ID")
reset = r.json()

print("Reset keys:", list(reset.keys()))
assert "observation" in reset, "FAIL: observation not nested"
assert "done" in reset,        "FAIL: missing done field"
assert "reward" in reset,      "FAIL: missing reward field"
assert reset["done"] == False, "FAIL: done should be false on reset"
assert reset["reward"] is None,"FAIL: reward should be null on reset"
print("PASS: observation is nested (official pattern)")
print(f"  Keys present: observation={bool(reset['observation'])}, done={reset['done']}, reward={reset['reward']}")

obs = reset["observation"]
print("\nObservation keys:", list(obs.keys()))
assert "scenario_id"  in obs, "FAIL: missing scenario_id"
assert "broken_sql"   in obs, "FAIL: missing broken_sql"
assert "difficulty"   in obs, "FAIL: missing difficulty"
print("PASS: observation contains required fields\n")

# Test 3: Step structure
print("=" * 60)
print("TEST 3: Step Response Structure")
step = requests.post(
    f"{BASE_URL}/step",
    json={"fixed_sql": "SELECT 1;", "explanation": "test", "confidence": 0.5},
    headers={"X-Session-ID": session_id},
).json()
print("Step keys:", list(step.keys()))
assert "reward" in step,      "FAIL: missing reward in step response"
assert "done"   in step,      "FAIL: missing done in step response"
assert "observation" in step, "FAIL: missing observation in step response"
assert "info" in step,        "FAIL: missing info in step response"
assert isinstance(step["reward"], float), "FAIL: reward must be float"
assert 0.0 <= step["reward"] <= 1.0,      "FAIL: reward out of [0.0, 1.0]"
print("PASS: step returns observation + reward + done + info")
print(f"  Reward={step['reward']} (range [0.0,1.0]) OK  Done={step['done']}\n")

# Test 4: State structure
print("=" * 60)
print("TEST 4: State Response Structure")
state = requests.get(f"{BASE_URL}/state", headers={"X-Session-ID": session_id}).json()
print("State keys:", list(state.keys()))
assert "step_count" in state, "FAIL: missing step_count"
assert "done"       in state, "FAIL: missing done"
assert "episode_id" in state, "FAIL: missing episode_id"
print("PASS: state check\n")

print("=" * 60)
print("=== ALL 4 CHECKS PASSED ===")
print(f"  /reset  → {{observation: {{...}}, done: false, reward: null}}")
print(f"  /step   → {{observation: {{...}}, reward: {step['reward']}, done: {step['done']}, info: {{...}}}}")
print(f"  /state  → {{step_count: {state['step_count']}, done: {state['done']}, ...}}")
print(f"  /health → {{status: healthy, scenarios_available: 24}}")
