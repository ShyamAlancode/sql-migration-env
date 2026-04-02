import sys
import os
import pytest

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.environment import get_env
from app.scenarios import ALL_SCENARIOS, DifficultyLevel

def test_deterministic_reset():
    """Ensure resetting by difficulty returns the first scenario of that difficulty for benchmark stability."""
    env = get_env()
    
    # Reset Hard twice
    obs1 = env.reset(difficulty=DifficultyLevel.HARD)
    id1 = obs1.scenario_id
    
    obs2 = env.reset(difficulty=DifficultyLevel.HARD)
    id2 = obs2.scenario_id
    
    assert id1 == id2
    # Benchmark tasks should be deterministic
    assert id1 == "hard_001_execution_order_corruption"

def test_no_hints_for_hard_scenarios():
    """Strictly verify that Hard scenarios yield no hints to the agent."""
    env = get_env()
    
    hard_scenarios = [s for s in ALL_SCENARIOS.values() if s.difficulty == DifficultyLevel.HARD]
    for scenario in hard_scenarios:
        obs = env.reset(scenario_id=scenario.id)
        assert obs.hint is None, f"Scenario {scenario.id} leaked a hint in HARD mode."

def test_observation_data_integrity():
    """Check that the environment returns correct metadata in observations."""
    env = get_env()
    obs = env.reset(difficulty=DifficultyLevel.EASY)
    
    assert obs.current_schema is not None
    assert obs.sample_data is not None
    # Check that it extracted the correct table
    assert len(obs.sample_data) >= 2 # Scenario setup has 2 rows (Alice, Bob)
