import sys
import os
import pytest

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.models import Action
from app.grader import MigrationGrader
from app.scenarios import get_scenario

def test_hard_009_circular_fk_validation():
    """
    Test Scenario 9: Circular Foreign Key.
    Requires table rebuild or PRAGMA trickery.
    """
    scenario = get_scenario("hard_009_circular_fk_dependency")
    grader = MigrationGrader(scenario)
    
    # 1. Naive fix: ALTER TABLE (SQLite unsupported)
    naive_fix = "ALTER TABLE employees ADD FOREIGN KEY (manager_id) REFERENCES employees(id);"
    result_naive = grader.grade(Action(fixed_sql=naive_fix))
    # It might 'succeed' syntax-wise but fail to apply the constraint
    assert result_naive.total_score < 50.0  # Should fail schema/integrity checks
    
    # 2. Expert fix: Table rebuild
    expert_fix = """
    PRAGMA foreign_keys=OFF;
    BEGIN TRANSACTION;
    CREATE TABLE employees_new (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        manager_id INTEGER,
        FOREIGN KEY (manager_id) REFERENCES employees_new(id)
    );
    INSERT INTO employees_new SELECT * FROM employees;
    DROP TABLE employees;
    ALTER TABLE employees_new RENAME TO employees;
    COMMIT;
    PRAGMA foreign_keys=ON;
    """
    result_expert = grader.grade(Action(fixed_sql=expert_fix))
    assert result_expert.total_score >= 80.0

def test_hard_010_hidden_data_loss_validation():
    """
    Test Scenario 10: Hidden Data Loss.
    Requires handling 'N/A' strings before CASTing to REAL.
    """
    scenario = get_scenario("hard_010_hidden_data_loss")
    grader = MigrationGrader(scenario)
    
    # 1. Naive fix: Simple re-creation with CAST
    # Telemetry data has 'N/A' and 'MISSING'. 
    # CAST('N/A' AS REAL) results in 0.0 or NULL depending on setup.
    # The scenario expects we don't have NULLs in reading_value.
    naive_fix = """
    CREATE TABLE new_telemetry (id INTEGER PRIMARY KEY, sensor_id TEXT, reading_value REAL);
    INSERT INTO new_telemetry SELECT id, sensor_id, CAST(reading_value AS REAL) FROM telemetry;
    DROP TABLE telemetry;
    ALTER TABLE new_telemetry RENAME TO telemetry;
    """
    result_naive = grader.grade(Action(fixed_sql=naive_fix))
    # This should fail because 'N/A' becomes NULL after CAST, and validation check counts NULLs.
    assert result_naive.data_integrity_score < 10.0
    
    # 2. Expert fix: Handle N/A stubs
    expert_fix = """
    CREATE TABLE telemetry_new (id INTEGER PRIMARY KEY, sensor_id TEXT, reading_value REAL);
    INSERT INTO telemetry_new SELECT id, sensor_id, 
        CASE 
            WHEN reading_value IN ('N/A', 'MISSING') THEN -1.0 
            ELSE CAST(reading_value AS REAL) 
        END 
    FROM telemetry;
    DROP TABLE telemetry;
    ALTER TABLE telemetry_new RENAME TO telemetry;
    """
    result_expert = grader.grade(Action(fixed_sql=expert_fix))
    assert result_expert.data_integrity_score >= 40.0

def test_hard_011_invisible_fk_validation():
    """
    Test Scenario 11: Invisible FK.
    REBUILD required when SQLite blocks simple ALTER due to self-referencing FK.
    """
    scenario = get_scenario("hard_011_invisible_fk_conflict")
    grader = MigrationGrader(scenario)
    
    # 1. Expert fix: Table rebuild
    # This also populates the 'slug' column which is needed for the validation check
    # Wait, the validation check is: SELECT COUNT(id) as count FROM categories WHERE name = 'Gaming Laptops' AND parent_id = 2
    # So we just need to preserve the data during rebuild.
    expert_fix = """
    PRAGMA foreign_keys=OFF;
    BEGIN TRANSACTION;
    CREATE TABLE categories_new (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        parent_id INTEGER,
        slug TEXT,
        FOREIGN KEY (parent_id) REFERENCES categories_new(id)
    );
    INSERT INTO categories_new (id, name, parent_id) SELECT id, name, parent_id FROM categories;
    DROP TABLE categories;
    ALTER TABLE categories_new RENAME TO categories;
    COMMIT;
    PRAGMA foreign_keys=ON;
    """
    result = grader.grade(Action(fixed_sql=expert_fix))
    assert result.data_integrity_score >= 40.0

def test_hard_012_ambiguous_join_validation():
    """
    Test Scenario 12: Ambiguous Join.
    Requires explicit aliasing to avoid corrupting user_id.
    """
    scenario = get_scenario("hard_012_ambiguous_join_corruption")
    grader = MigrationGrader(scenario)
    
    # 1. Naive fix: Ambiguous join
    naive_fix = "UPDATE profile SET user_id = (SELECT id FROM users WHERE users.id = profile.id);"
    # result: profile.id is 101, user.id is 2 max? No, it will likely return NULL or result in 101 which is wrong
    result_naive = grader.grade(Action(fixed_sql=naive_fix))
    assert result_naive.data_integrity_score < 40.0
    
    # 2. Expert fix: Precise aliasing
    # Wait, the target is profile.user_id = 1. profile.id = 101. users.id = 1.
    expert_fix = "UPDATE profile SET user_id = (SELECT id FROM users WHERE users.id = profile.user_id);"
    result_expert = grader.grade(Action(fixed_sql=expert_fix))
    assert result_expert.data_integrity_score >= 40.0

