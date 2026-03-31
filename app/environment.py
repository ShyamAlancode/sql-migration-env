"""
Core OpenEnv Environment for SQL Migration Safety Gym
Implements: reset(), step(), state() API
"""

from typing import Tuple, Dict, Any, Optional
from app.models import Action, Observation, State, DifficultyLevel, GradingResult
from app.scenarios import get_scenario, ALL_SCENARIOS
from app.grader import MigrationGrader
from app.database import sandbox_db
import uuid


class SQLMigrationEnv:
    """
    OpenEnv-compliant environment for SQL migration fixing.
    
    Usage:
        env = SQLMigrationEnv()
        obs = env.reset(scenario_id="easy_001")
        obs, reward, done, info = env.step(action)
    """
    
    def __init__(self, max_steps: int = 5):
        self.max_steps = max_steps
        self._current_scenario_id: Optional[str] = None
        self._step_count: int = 0
        self._done: bool = False
        self._history: list = []
        self._episode_id: Optional[str] = None
        self._current_db_hash: Optional[str] = None
        self._last_grading_result: Optional[GradingResult] = None
        
    def reset(self, scenario_id: Optional[str] = None, 
              difficulty: Optional[DifficultyLevel] = None) -> Observation:
        """
        Reset environment to initial state.
        
        Args:
            scenario_id: Specific scenario to load (random if None)
            difficulty: Filter scenarios by difficulty (random if None)
            
        Returns:
            Initial observation
        """
        # Select scenario
        if scenario_id:
            self._current_scenario_id = scenario_id
        else:
            # Random selection
            import random
            candidates = list(ALL_SCENARIOS.values())
            if difficulty:
                candidates = [s for s in candidates if s.difficulty == difficulty]
            scenario = random.choice(candidates)
            self._current_scenario_id = scenario.id
        
        # Reset state
        self._step_count = 0
        self._done = False
        self._history = []
        self._episode_id = str(uuid.uuid4())
        self._last_grading_result = None
        
        # Initialize database for observation generation
        scenario = get_scenario(self._current_scenario_id)
        with sandbox_db() as db:
            db.execute_script(scenario.setup_sql)
            
            # Try running broken migration to capture error
            success, error = db.execute_script(scenario.broken_migration)
            error_msg = error if not success else None
            
            # Capture state
            self._current_db_hash = db.compute_hash()
            
            # Build observation
            obs = self._build_observation(db, scenario, error_msg)
            
        return obs
    
    def step(self, action: Action) -> Tuple[Observation, float, bool, Dict[str, Any]]:
        """
        Execute one step in the environment.
        
        Args:
            action: Agent's proposed fix
            
        Returns:
            Tuple of (observation, reward, done, info)
        """
        if self._done:
            raise RuntimeError("Episode is done. Call reset() to start new episode.")
        
        if not self._current_scenario_id:
            raise RuntimeError("Environment not reset. Call reset() first.")
        
        # Get scenario and grade action
        scenario = get_scenario(self._current_scenario_id)
        grader = MigrationGrader(scenario)
        grading_result = grader.grade(action)
        self._last_grading_result = grading_result
        
        # Calculate reward (0-100 scale normalized to 0-1, or keep as 0-100)
        reward = grading_result.total_score / 100.0
        
        # Bonus for silent corruption detection
        if (scenario.is_silent_corruption and 
            grading_result.silent_corruption_detected and 
            grading_result.data_integrity_score >= 40):
            reward += 0.1
        
        # Efficiency penalty per step (small)
        reward -= 0.01
        
        # Clamp reward
        reward = max(0.0, min(1.0, reward))
        
        # Increment step
        self._step_count += 1
        
        # Check termination conditions
        if grading_result.total_score >= 95:
            self._done = True  # Perfect fix
        elif self._step_count >= self.max_steps:
            self._done = True  # Max steps reached
        
        # Record history
        self._history.append({
            "step": self._step_count,
            "action": action.model_dump(),
            "grading": grading_result.model_dump(),
            "reward": reward
        })
        
        # Generate next observation
        with sandbox_db() as db:
            # Re-setup database for clean observation (or keep state?)
            # For migration tasks, we reset to show current state
            db.execute_script(scenario.setup_sql)
            
            # If we wanted to simulate progressive fixing, we'd apply action here
            # But for this env, each step is independent evaluation
            
            obs = self._build_observation(db, scenario, None)  # No error on observation
        
        info = {
            "episode_id": self._episode_id,
            "step": self._step_count,
            "grading_result": grading_result.model_dump(),
            "scenario_id": self._current_scenario_id,
            "difficulty": scenario.difficulty.value
        }
        
        return obs, reward, self._done, info
    
    def state(self) -> Dict[str, Any]:
        """
        Get current environment state (internal state, not observation).
        Per OpenEnv spec: returns step count, done flag, history, etc.
        """
        if not self._current_scenario_id:
            raise RuntimeError("Environment not reset. Call reset() first.")
        
        return {
            "task_id": self._current_scenario_id,
            "step_count": self._step_count,
            "done": self._done,
            "max_steps": self.max_steps,
            "history": self._history,
            "episode_id": self._episode_id
        }

    def observation(self) -> Observation:
        """
        Get current observation (what agent sees).
        This is separate from state() per spec.
        """
        if not self._current_scenario_id:
            raise RuntimeError("Environment not reset. Call reset() first.")
        
        scenario = get_scenario(self._current_scenario_id)
        with sandbox_db() as db:
            db.execute_script(scenario.setup_sql)
            return self._build_observation(db, scenario, None)
    
    def _build_observation(self, db, scenario, error_msg: Optional[str]) -> Observation:
        """Construct observation from current database state"""
        # Get table info (assume first table is main table)
        tables = db.get_table_names()
        current_schema = None
        sample_data = None
        previous_schema = None
        
        if tables:
            main_table = tables[0]
            current_schema_data = db.get_schema_info(main_table)
            if current_schema_data:
                from app.models import SchemaInfo
                current_schema = SchemaInfo(**current_schema_data)
            sample_data = db.get_sample_data(main_table, limit=5)
            
            # For "previous" schema, we'd need to track this across steps
            # For now, same as current or None
            previous_schema = current_schema
        
        # Hint only for easy mode
        hint = scenario.hint if scenario.difficulty == DifficultyLevel.EASY else None
        
        return Observation(
            scenario_id=scenario.id,
            difficulty=scenario.difficulty,
            broken_sql=scenario.broken_migration,
            error_message=error_msg,
            current_schema=current_schema,
            previous_schema=previous_schema,
            sample_data=sample_data,
            hint=hint,
            step_count=self._step_count,
            max_steps=self.max_steps
        )
    
    def get_episode_stats(self) -> Dict[str, Any]:
        """Get statistics for current/completed episode"""
        if not self._episode_id:
            return {}
        
        total_reward = sum(h["reward"] for h in self._history)
        avg_score = sum(h["grading"]["total_score"] for h in self._history) / len(self._history) if self._history else 0
        
        return {
            "episode_id": self._episode_id,
            "scenario_id": self._current_scenario_id,
            "total_steps": self._step_count,
            "total_reward": total_reward,
            "average_score": avg_score,
            "history": self._history,
            "done": self._done
        }


# Global environment instance (for HF Spaces stateful deployment)
_env_instance: Optional[SQLMigrationEnv] = None

def get_env() -> SQLMigrationEnv:
    """Get or create global environment instance"""
    global _env_instance
    if _env_instance is None:
        _env_instance = SQLMigrationEnv()
    return _env_instance
