"""
Deterministic grading engine for sql-migration-env
Scores: Syntax (20), Data Integrity (40), Schema (30), Efficiency (10)
"""

import sqlite3
import json
import re
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
            
            # Dispatch to specialized grader for the new hard scenario
            if self.scenario.id == "hard_001_execution_order_corruption":
                return self._grade_hard_execution_order(
                    db, pre_hash, exec_success, exec_error
                )

            # Score components
            syntax_score = self._grade_syntax(exec_success, exec_error)
            data_score, corruption_flag = self._grade_data_integrity(
                db, pre_data, post_data, pre_hash, post_hash
            )
            schema_score = self._grade_schema_correctness(db)
            efficiency_score = self._grade_efficiency(action.fixed_sql)
            
            # Weighted total: 10 + 45 + 35 + 10 = 100
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
        """10 points for valid SQL execution without crash"""
        return 10.0 if success else 0.0
    
    def _grade_data_integrity(
        self, db, pre_data: Dict, post_data: Dict, 
        pre_hash: str, post_hash: str
    ) -> Tuple[float, bool]:
        """
        45 points for preserving and verifying data integrity.
        Uses scenario-specific validation queries even for Easy/Medium.
        """
        # Execute validation queries and compare to expected results
        total_queries = len(self.scenario.validation_queries)
        passed_queries = 0
        all_pass = True
        
        for i, query in enumerate(self.scenario.validation_queries):
            success, actual_rows, _ = db.execute_query(query)
            if not success:
                all_pass = False
                continue
            
            expected_rows = self.scenario.expected_results[i]
            if self._rows_match(actual_rows, expected_rows):
                passed_queries += 1
            else:
                all_pass = False
        
        # Smooth scoring: proportional to passed queries
        data_score = 45.0 * (passed_queries / total_queries) if total_queries > 0 else 45.0

        # SHA-256 as side-effect guardrail and "Gold Standard" bonus
        hash_matched = (pre_hash == post_hash) # Flat check for no change
        
        # If the environment HAS a known final hash in scenario metadata (TBD in future spec)
        # For now, we reward the absence of unexplained side-effects
        if all_pass:
            if hash_matched:
                # Perfect score: passed validation with ZERO side-effects
                data_score = 45.0
            else:
                # 40.0 points: passed validation but changed database in undocumented ways
                # This catches agents that 'spray and pray' updates
                data_score = 40.0
        else:
            # 0.0 points: primary validation failed
            data_score = 0.0
            
        corruption_detected = not all_pass  # Primary signal: validation failure
        
        return max(0.0, data_score), corruption_detected
    
    def _grade_schema_correctness(self, db) -> float:
        """35 points for achieving the intended schema"""
        if not self.scenario.expected_schema:
            # Fallback to validation query verification if no explicit schema provided
            all_pass = True
            for i, query in enumerate(self.scenario.validation_queries):
                success, actual_rows, _ = db.execute_query(query)
                if not success:
                    all_pass = False
                    continue
                expected_rows = self.scenario.expected_results[i]
                if not self._rows_match(actual_rows, expected_rows):
                    all_pass = False
            return 35.0 if all_pass else 0.0

        # High-fidelity schema comparison
        actual = db.get_schema_info(self.scenario.expected_schema.table_name)
        if not actual:
            return 0.0
        
        expected_cols = {(c["name"], str(c["type"]).upper()) for c in self.scenario.expected_schema.columns}
        actual_cols = {(c["name"], str(c["type"]).upper()) for c in actual["columns"]}
        
        # Smooth scoring: fractional points for every correct column
        matching = expected_cols.intersection(actual_cols)
        ratio = len(matching) / len(expected_cols)
        schema_score = 35.0 * ratio

        # Penalize for extra/unintended columns
        if len(actual_cols) > len(expected_cols):
            schema_score -= 5.0
            
        return max(0.0, schema_score)
    
    def _grade_efficiency(self, sql: str) -> float:
        """10 points for efficient SQL (no redundant ops, proper syntax)"""
        score = 10.0
        upper = sql.upper()
        
        # Penalize obvious inefficiencies
        if upper.count("ALTER TABLE") > 3:
            score -= 3  # Too many alter statements
        
        if "DROP TABLE" in upper and "CREATE TABLE" in upper:
            score -= 5  # Destructive recreation instead of ALTER
        
        if "SELECT *" in upper and any(s.is_silent_corruption for s in [self.scenario]):
            # Discourage SELECT * in complex/hard scenarios
            score -= 2
        
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

    def _grade_hard_execution_order(
        self,
        db,
        pre_hash: str,
        exec_success: bool,
        exec_error: str
    ) -> GradingResult:
        """
        Grades the execution-order corruption scenario.
        Only way to get full score: reorder UPDATE to run after
        discount_pct is populated, not immediately after ALTER TABLE.
        """

        # Execution failure = near zero
        if not exec_success:
            return GradingResult(
                total_score=5.0,
                syntax_correct=False,
                syntax_score=0.0,
                data_integrity_score=0.0,
                schema_correct_score=0.0,
                efficiency_score=5.0,
                silent_corruption_detected=False,
                detailed_feedback=f"Execution error: {exec_error}"
            )

        post_hash = db.compute_hash()
        syntax_score = 20.0  # executed cleanly

        # Check premium customer discounts
        try:
            # Use db.connection.execute as prescribed in the task
            rows = db.connection.execute(
                "SELECT id, customer_tier, discount_pct, final_amount, total_amount "
                "FROM orders ORDER BY id"
            ).fetchall()
            rows = [dict(r) for r in rows]
        except Exception as e:
            return GradingResult(
                total_score=20.0,
                syntax_correct=True,
                syntax_score=20.0,
                data_integrity_score=0.0,
                schema_correct_score=0.0,
                efficiency_score=0.0,
                detailed_feedback=f"Validation query failed: {e}"
            )

        # Score premium discount correctness
        premium_rows = [r for r in rows if r["customer_tier"] == "premium"]
        standard_rows = [r for r in rows if r["customer_tier"] == "standard"]

        premium_correct = 0
        for row in premium_rows:
            actual_discount = row.get("discount_pct", 0)
            # Check discount_pct > 0 (not the silent corruption zero)
            if actual_discount > 0.01:
                premium_correct += 1

        standard_correct = all(
            r.get("discount_pct", -1) < 0.01
            for r in standard_rows
        )

        premium_ratio = premium_correct / len(premium_rows) if premium_rows else 0.0

        # Data integrity score: 0-40
        if premium_ratio >= 1.0 and standard_correct:
            data_score = 40.0
        elif premium_ratio >= 0.5:
            data_score = 20.0
        elif premium_ratio > 0:
            data_score = 10.0
        else:
            # Silent corruption still present: all zeros
            data_score = 0.0

        # final_amount correctness: 0-30
        schema_score = 0.0
        try:
            correct_finals = 0
            for row in rows:
                # Simpler check: final_amount > 0 and less than total_amount
                # for premium, final_amount < total_amount
                if row["customer_tier"] == "premium":
                    if row.get("final_amount", 0) < row.get("total_amount", 999):
                        correct_finals += 1
                else:
                    if abs(row.get("final_amount", 0) - row.get("total_amount", 0)) < 0.01:
                        correct_finals += 1

            schema_score = 30.0 * (correct_finals / len(rows))
        except Exception:
            schema_score = 0.0

        efficiency_score = 10.0 if not re.search(
            r'\bDROP\b|\bTRUNCATE\b', str(db), re.I
        ) else 0.0

        total = syntax_score + data_score + schema_score + efficiency_score
        corruption_present = (data_score == 0.0)

        return GradingResult(
            total_score=round(min(100.0, total), 2),
            syntax_correct=True,
            syntax_score=syntax_score,
            data_integrity_score=round(data_score, 2),
            schema_correct_score=round(schema_score, 2),
            efficiency_score=efficiency_score,
            silent_corruption_detected=corruption_present,
            detailed_feedback=(
                f"Premium discounts correct: {premium_correct}/{len(premium_rows)}. "
                f"Corruption present: {corruption_present}"
            )
        )


def grade_submission(scenario_id: str, action: Action) -> GradingResult:
    """Convenience function for grading"""
    scenario = MigrationScenario.get_scenario(scenario_id)
    grader = MigrationGrader(scenario)
    return grader.grade(action)


# Monkey-patch get_scenario onto MigrationScenario for convenience
MigrationScenario.get_scenario = staticmethod(lambda sid: ALL_SCENARIOS[sid])
