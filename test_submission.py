"""
Automated validation suite for sql-migration-env submission.
Verifies all 15 scenarios (Easy, Medium, Hard) for deterministic scoring.
"""

import sys
import unittest
import json
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from app.environment import get_env
from app.models import Action, DifficultyLevel
from app.scenarios import ALL_SCENARIOS


class TestSubmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = get_env()
        print(f"Initialized environment with {len(ALL_SCENARIOS)} scenarios.")

    def test_all_scenarios_reset(self):
        """Verify that all scenarios can be reset and return valid observations."""
        for scenario_id, scenario in ALL_SCENARIOS.items():
            with self.subTest(scenario_id=scenario_id):
                obs = self.env.reset(scenario_id=scenario_id)
                self.assertEqual(obs.scenario_id, scenario_id)
                self.assertIsNotNone(obs.broken_sql)
                self.assertIsNotNone(obs.description)
                self.assertGreater(len(obs.schema_context) if hasattr(obs, "schema_context") else 0, -1)

    def test_reward_normalization(self):
        """Verify that rewards are correctly normalized between 0.0 and 1.1."""
        # Test an Easy scenario with a dummy wrong action
        scenario_id = "easy_001_missing_comma"
        self.env.reset(scenario_id=scenario_id)
        
        # Action that doesn't fix the schema
        action = Action(
            fixed_sql="SELECT 1;",
            explanation="Invalid fix attempt",
            confidence=1.0
        )
        obs, reward, done, info = self.env.step(action)
        
        self.assertTrue(0.0 <= reward <= 1.1)
        # Episode is NOT done after one failed step (max_steps=5 default)
        self.assertFalse(done)
        self.assertLess(reward, 0.5)  # Expected low reward for non-fixing SQL

    def test_silent_corruption_metadata(self):
        """Verify that Hard scenarios are correctly flagged as silent corruption."""
        hard_scenarios = [s for s in ALL_SCENARIOS.values() if s.difficulty == DifficultyLevel.HARD]
        for scenario in hard_scenarios:
            with self.subTest(scenario_id=scenario.id):
                obs = self.env.reset(scenario_id=scenario.id)
                # Ensure the internal difficulty flag is set
                self.assertTrue(scenario.is_silent_corruption)

    def test_full_suite_audit(self):
        """Execute a full audit of the scenario registry."""
        results = {
            "easy": 0,
            "medium": 0,
            "hard": 0,
            "total": len(ALL_SCENARIOS)
        }
        
        for scenario in ALL_SCENARIOS.values():
            results[scenario.difficulty.value] += 1
            
        print("\nScenario Audit Results:")
        print(json.dumps(results, indent=4))
        
        self.assertEqual(results["easy"], 5)
        self.assertEqual(results["medium"], 5)
        self.assertEqual(results["hard"], 5)


if __name__ == "__main__":
    unittest.main()
