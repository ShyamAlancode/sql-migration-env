import sys
import os
import pytest

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import Action, DifficultyLevel
from app.grader import MigrationGrader
from app.scenarios import get_scenario

def test_easy_scenario_grader():
    """Test grader on a basic syntax error scenario"""
    scenario = get_scenario("easy_001_missing_comma")
    grader = MigrationGrader(scenario)
    
    # Good fix: Scenario expects email (NOT NULL) and age
    action_good = Action(fixed_sql="ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''; ALTER TABLE users ADD COLUMN age INTEGER;")
    result_good = grader.grade(action_good)
    assert result_good.syntax_correct is True
    assert result_good.syntax_score == 10.0
    assert result_good.total_score >= 90.0

def test_hard_execution_order_grader():
    """Test grader on the complex execution-order scenario"""
    scenario = get_scenario("hard_001_execution_order_corruption")
    grader = MigrationGrader(scenario)
    
    # Correct fix: Reorder so columns exist before updates that depend on them
    correct_fix = """
        BEGIN TRANSACTION;
        ALTER TABLE orders ADD COLUMN discount_pct REAL DEFAULT 0.0;
        ALTER TABLE orders ADD COLUMN final_amount REAL DEFAULT 0.0;
        UPDATE orders SET discount_pct = total_amount * 0.10 WHERE customer_tier = 'premium';
        UPDATE orders SET final_amount = total_amount * (1.0 - discount_pct);
        COMMIT;
    """
    action = Action(fixed_sql=correct_fix)
    result = grader.grade(action)
    assert result.data_integrity_score == 40.0
    assert result.silent_corruption_detected is False

def test_schema_smooth_scoring():
    """Test that partial schema changes receive partial credit"""
    scenario = get_scenario("easy_001_missing_comma") # expects age and bio
    grader = MigrationGrader(scenario)
    
    # Partial fix (only adds age, missing bio)
    partial_sql = "ALTER TABLE users ADD COLUMN age INTEGER;"
    result = grader.grade(Action(fixed_sql=partial_sql))
    
    # Base cols: id, username. Expected additions: age, bio. Total=4.
    # Partial fix has: id, username, age. Total=3.
    # Ratio = 3/4 = 0.75. Score = 35 * 0.75 = 26.25.
    assert 26.0 <= result.schema_correct_score <= 27.0

@pytest.mark.parametrize("scenario_id", [
    "hard_009_circular_fk_dependency",
    "hard_010_hidden_data_loss"
])
def test_impossible_scenarios_exist(scenario_id):
    """Ensure the new 'Impossible' tasks are registered and loadable"""
    scenario = get_scenario(scenario_id)
    assert scenario.difficulty == DifficultyLevel.HARD
    assert scenario.hint is None
