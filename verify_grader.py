
import sys
import os
from unittest.mock import MagicMock

# Add current directory to path
sys.path.append(os.getcwd())

from app.models import Action, DifficultyLevel
from app.grader import MigrationGrader
from app.scenarios import get_scenario

def test_hard_scenario_grader():
    scenario = get_scenario("hard_001_execution_order_corruption")
    grader = MigrationGrader(scenario)

    # 1. Agent just adds WHERE clause (Silent Corruption remains)
    broken_fix = """
        BEGIN TRANSACTION;
        ALTER TABLE orders ADD COLUMN discount_pct REAL DEFAULT 0.0;
        UPDATE orders
            SET discount_pct = total_amount * 0.10
            WHERE customer_tier = 'premium';
        ALTER TABLE orders ADD COLUMN final_amount REAL DEFAULT 0.0;
        UPDATE orders
            SET final_amount = total_amount * (1.0 - discount_pct)
            WHERE customer_tier = 'premium';
        COMMIT;
    """
    action1 = Action(fixed_sql=broken_fix, explanation="Added WHERE clause")
    result1 = grader.grade(action1)
    print(f"--- Rule-based (add WHERE) ---")
    print(f"Total Score: {result1.total_score}")
    print(f"Data Integrity: {result1.data_integrity_score}")
    print(f"Feedback: {result1.detailed_feedback}")

    # 2. Agent correctly reorders
    correct_fix = """
        BEGIN TRANSACTION;
        ALTER TABLE orders ADD COLUMN discount_pct REAL DEFAULT 0.0;
        ALTER TABLE orders ADD COLUMN final_amount REAL DEFAULT 0.0;
        
        -- Population must happen AFTER columns are added
        UPDATE orders
            SET discount_pct = total_amount * 0.10
            WHERE customer_tier = 'premium';
            
        UPDATE orders
            SET final_amount = total_amount * (1.0 - discount_pct);
        COMMIT;
    """
    action2 = Action(fixed_sql=correct_fix, explanation="Reordered updates")
    result2 = grader.grade(action2)
    print(f"\n--- Correct Fix (Reordered) ---")
    print(f"Total Score: {result2.total_score}")
    print(f"Data Integrity: {result2.data_integrity_score}")
    print(f"Feedback: {result2.detailed_feedback}")

if __name__ == "__main__":
    test_hard_scenario_grader()
