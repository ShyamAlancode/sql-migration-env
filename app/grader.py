"""
Deterministic grading engine for sql-migration-env
Scores: Syntax (20), Data Integrity (40), Schema (30), Efficiency (10)
"""

import sqlite3
import json
from typing import Tuple, List, Dict, Any
from app.models import Action, GradingResult, MigrationScenario, DifficultyLevel
from app.database import sandbox_db
from app.scenarios import ALL_SCENARIOS


class MigrationGrader:
    """
    Deterministic grader for SQL migration fixes.
    Critical for 25% of hackathon judging score!
    """
    
    def __init__(self, scenario: MigrationScenario):
        self.scenario = scenario
        
    def grade(self, action: Action) -> GradingResult:
        """
        Grade an agent's proposed fix.
        Returns detailed breakdown and total score.
        """
        with sandbox_db() as db:
            # Step 1: Setup baseline
            setup_success, setup_error = db.execute_script(self.scenario.setup_sql)
            if not setup_success:
                raise RuntimeError(f"Setup failed: {setup_error}")
            
            # Capture pre-migration state
            pre_hash = db.compute_hash()
            pre_data = self._capture_table_data(db)
            
            # Step 2: Execute agent's fix
            exec_success, exec_error = db.execute_script(action.fixed_sql)
            
            if not exec_success:
                # Syntax error - immediate failure on syntax component
                return GradingResult(
                    total_score=0.0,
                    syntax_correct=False,
                    syntax_score=0.0,
                    data_integrity_score=0.0,
                    schema_correct_score=0.0,
                    efficiency_score=0.0,
                    detailed_feedback=f"Syntax/Execution Error: {exec_error}",
                    silent_corruption_detected=None
                )
            
            # Step 3: Analyze results
            post_hash = db.compute_hash()
            post_data = self._capture_table_data(db)
            
            # Score components
            syntax_score = self._grade_syntax(exec_success, exec_error)
            data_score, corruption_flag = self._grade_data_integrity(
                db, pre_data, post_data, pre_hash, post_hash
            )
            schema_score = self._grade_schema_correctness(db)
            efficiency_score = self._grade_efficiency(action.fixed_sql)
            
            total = syntax_score + data_score + schema_score + efficiency_score
            
            feedback = self._generate_feedback(
                syntax_score, data_score, schema_score, efficiency_score,
                corruption_flag, action.explanation
            )
            
            return GradingResult(
                total_score=round(total, 2),
                syntax_correct=True,
                syntax_score=round(syntax_score, 2),
                data_integrity_score=round(data_score, 2),
                schema_correct_score=round(schema_score, 2),
                efficiency_score=round(efficiency_score, 2),
                detailed_feedback=feedback,
                silent_corruption_detected=corruption_flag if self.scenario.is_silent_corruption else None
            )
    
    def _capture_table_data(self, db) -> Dict[str, List[Dict]]:
        """Capture all table data for comparison"""
        data = {}
        for table in db.get_table_names():
            success, rows, _ = db.execute_query(f"SELECT * FROM {table}")
            if success:
                data[table] = rows
        return data
    
    def _grade_syntax(self, success: bool, error: str | None) -> float:
        """20 points for valid SQL execution"""
        return 20.0 if success else 0.0
    
    def _grade_data_integrity(
        self, db, pre_data: Dict, post_data: Dict, 
        pre_hash: str, post_hash: str
    ) -> Tuple[float, bool]:
        """
        40 points for preserving existing data.
        CRITICAL for HARD mode (silent corruption detection).
        """
        if not self.scenario.is_silent_corruption:
            # Standard mode: Check that we didn't lose rows
            score = 40.0
            for table, pre_rows in pre_data.items():
                post_rows = post_data.get(table, [])
                if len(post_rows) < len(pre_rows):
                    # Data loss!
                    loss_ratio = (len(pre_rows) - len(post_rows)) / len(pre_rows)
                    score -= 40.0 * loss_ratio
            return max(0.0, score), False
        else:
            # HARD MODE: Silent corruption detection
            # The scenario setup is designed so that the BROKEN SQL corrupts data
            # The FIXED SQL should restore/prevent corruption
            
            # Check if validation queries pass
            all_pass = True
            for i, query in enumerate(self.scenario.validation_queries):
                success, actual_rows, _ = db.execute_query(query)
                if not success:
                    all_pass = False
                    continue
                
                expected_rows = self.scenario.expected_results[i]
                if not self._rows_match(actual_rows, expected_rows):
                    all_pass = False
            
            # Also check hash changed appropriately
            corruption_detected = (pre_hash != post_hash)
            
            if all_pass:
                return 40.0, corruption_detected
            else:
                # Partial credit if some data preserved
                return 10.0, corruption_detected
    
    def _grade_schema_correctness(self, db) -> float:
        """30 points for achieving intended schema"""
        if not self.scenario.expected_schema:
            # Check if they used CREATE UNIQUE INDEX instead of ALTER TABLE ADD CONSTRAINT
            # This is valid SQLite workaround - give full credit!
            if "unique" in self.scenario.description.lower():
                # Check for unique index as alternative
                success, unique_indexes, _ = db.execute_query(
                    "SELECT name FROM sqlite_master WHERE type='index' AND sql LIKE '%UNIQUE%'"
                )
                if success and len(unique_indexes) > 0:
                    return 30.0  # Full credit for workaround
            
            # Check validation queries
            all_pass = True
            for i, query in enumerate(self.scenario.validation_queries):
                success, actual_rows, _ = db.execute_query(query)
                if not success:
                    all_pass = False
                    continue
                expected_rows = self.scenario.expected_results[i]
                if not self._rows_match(actual_rows, expected_rows):
                    all_pass = False
                    
            return 30.0 if all_pass else 0.0

        # Compare actual schema to expected
        actual = db.get_schema_info(self.scenario.expected_schema.table_name)
        if not actual:
            return 0.0
        
        score = 30.0
        
        # Check columns match
        expected_cols = {(c["name"], str(c["type"]).upper()) for c in self.scenario.expected_schema.columns}
        actual_cols = {(c["name"], str(c["type"]).upper()) for c in actual["columns"]}
        
        if expected_cols != actual_cols:
            missing = expected_cols - actual_cols
            extra = actual_cols - expected_cols
            penalty = min(30.0, (len(missing) + len(extra)) * 10) # increase penalty
            score -= penalty
        
        return max(0.0, score)
    
    def _grade_efficiency(self, sql: str) -> float:
        """10 points for efficient SQL (no redundant ops, proper syntax)"""
        score = 10.0
        upper = sql.upper()
        
        # Penalize obvious inefficiencies
        if upper.count("ALTER TABLE") > 3:
            score -= 3  # Too many alter statements
        
        if "DROP TABLE" in upper and "CREATE TABLE" in upper:
            score -= 5  # Destructive recreation instead of ALTER
        
        if ";" * 5 in sql:  # Multiple semicolons (empty statements)
            score -= 2
        
        return max(0.0, score)
    
    def _rows_match(self, actual: List[Dict], expected: List[Dict]) -> bool:
        """Compare query results with tolerance for type differences"""
        if len(actual) != len(expected):
            return False
        
        for a_row, e_row in zip(actual, expected):
            # Check keys match
            if set(a_row.keys()) != set(e_row.keys()):
                return False
            
            for key in a_row:
                a_val, e_val = a_row[key], e_row[key]
                
                # Handle None values
                if a_val is None and e_val is None:
                    continue
                elif a_val is None or e_val is None:
                    return False
                    
                # Handle numeric tolerance
                if isinstance(e_val, (int, float)) and isinstance(a_val, (int, float)):
                    if abs(float(a_val) - float(e_val)) > 0.01:
                        return False
                elif str(a_val) != str(e_val):
                    return False
        
        return True
    
    def _generate_feedback(
        self, syntax: float, data: float, schema: float, efficiency: float,
        corruption_flag: bool, explanation: str
    ) -> str:
        """Generate human-readable feedback"""
        parts = []
        
        if syntax < 20:
            parts.append("Syntax error in fixed SQL.")
        else:
            parts.append("SQL executed successfully.")
        
        if self.scenario.is_silent_corruption:
            if data >= 40:
                parts.append("EXCELLENT: Silent corruption prevented/fixed!")
            elif data > 20:
                parts.append("WARNING: Partial data corruption.")
            else:
                parts.append("CRITICAL: Silent data corruption detected!")
        
        if schema < 30:
            parts.append("Schema does not match expected state.")
        
        if efficiency < 10:
            parts.append("Consider optimizing migration approach.")
        
        if explanation:
            parts.append(f"Agent explanation: {explanation[:200]}")
        
        return " ".join(parts)


def grade_submission(scenario_id: str, action: Action) -> GradingResult:
    """Convenience function for grading"""
    scenario = MigrationScenario.get_scenario(scenario_id)
    grader = MigrationGrader(scenario)
    return grader.grade(action)


# Monkey-patch get_scenario onto MigrationScenario for convenience
MigrationScenario.get_scenario = staticmethod(lambda sid: ALL_SCENARIOS[sid])
