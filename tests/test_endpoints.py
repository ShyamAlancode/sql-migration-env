import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_reset_endpoint():
    response = client.post("/reset", json={"task_id": "easy"})
    assert response.status_code == 200
    data = response.json()
    assert "observation" in data
    assert data["done"] is False
    assert data["observation"]["difficulty"] == "easy"

def test_step_endpoint():
    # Reset first
    client.post("/reset", json={"task_id": "easy"})
    # Step
    response = client.post("/step", json={
        "fixed_sql": "SELECT 1;",
        "explanation": "test fix",
        "confidence": 0.9
    })
    assert response.status_code == 200
    data = response.json()
    assert "reward" in data
    assert "observation" in data
    assert "done" in data

def test_session_isolation():
    # Session A
    resp_a = client.post("/reset", json={"task_id": "easy"}, headers={"X-Session-ID": "session-a"})
    id_a = resp_a.json()["observation"]["scenario_id"]
    
    # Session B
    resp_b = client.post("/reset", json={"task_id": "hard"}, headers={"X-Session-ID": "session-b"})
    id_b = resp_b.json()["observation"]["scenario_id"]
    
    assert id_a != id_b
    
    # Check state isolation
    state_a = client.get("/state", headers={"X-Session-ID": "session-a"}).json()
    assert state_a["task_id"] == id_a
