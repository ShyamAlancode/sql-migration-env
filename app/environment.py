"""
Core OpenEnv Environment for SQL Migration Safety Gym
Implements: reset(), step(), state(), observation() API per RFC 001
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
    Strict separation of state() vs observation() per spec.
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
        Returns: Initial observation (what agent sees)
        """
        # Select scenario
        if scenario_id:
            self._current_scenario_id = scenario_id
        else:
            import random
            candidates = list(ALL_SCENARIOS.values())
            if difficulty:
                candidates = [s for s in candidates if s.difficulty == difficulty]
            scenario = random.choice(candidates)
            self._current_scenario_id = scenario.id
        
        # Reset internal state
        self._step_count = 0
        self._done = False
        self._history = []
        self._episode_id = str(uuid.uuid4())
        self._last_grading_result = None
        
        # Generate and return observation
        scenario = get_scenario(self._current_scenario_id)
        with sandbox_db() as db:
            db.execute_script(scenario.setup_sql)
            success, error = db.execute_script(scenario.broken_migration)
            error_msg = error if not success else None
            obs = self._build_observation(db, scenario, error_msg)
            
        return obs
    
    def step(self, action: Action) -> Tuple[Observation, float, bool, Dict[str, Any]]:
        """
        Execute one step.
        Returns: (observation, reward, done, info)
        """
        if self._done:
            raise RuntimeError("Episode is done. Call reset() to start new episode.")
        
        if not self._current_scenario_id:
            raise RuntimeError("Environment not reset. Call reset() first.")
        
        # Grade action
        scenario = get_scenario(self._current_scenario_id)
        grader = MigrationGrader(scenario)
        grading_result = grader.grade(action)
        self._last_grading_result = grading_result
        
        # Calculate reward (0-1 scale)
        reward = grading_result.total_score / 100.0
        if (scenario.is_silent_corruption and 
            grading_result.data_integrity_score >= 40):
            reward += 0.1
        reward = max(0.0, min(1.0, reward))
        reward = round(reward, 4)  # Round for cleaner output
        
        # Update internal state
        self._step_count += 1
        
        # Check termination
        if grading_result.total_score >= 95:
            self._done = True
        elif self._step_count >= self.max_steps:
            self._done = True
        
        # Record in history
        self._history.append({
            "step": self._step_count,
            "action": action.model_dump(),
            "grading": grading_result.model_dump(),
            "reward": reward
        })
        
        # Generate next observation
        with sandbox_db() as db:
            db.execute_script(scenario.setup_sql)
            obs = self._build_observation(db, scenario, None)
            obs.step_count = self._step_count
        
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
        Return INTERNAL STATE (not observation).
        Per OpenEnv spec: episode metadata, step count, done flag, history.
        Used by environment tracking, NOT shown to agent.
        """
        if not self._episode_id:
            return {
                "episode_id": None,
                "task_id": None,
                "step_count": 0,
                "max_steps": self.max_steps,
                "done": False,
                "history_length": 0,
                "total_reward": 0.0
            }
        
        total_reward = sum(h["reward"] for h in self._history)
        
        return {
            "episode_id": self._episode_id,
            "task_id": self._current_scenario_id,
            "step_count": self._step_count,
            "max_steps": self.max_steps,
            "done": self._done,
            "history_length": len(self._history),
            "total_reward": round(total_reward, 4),
            "last_score": self._history[-1]["grading"]["total_score"] if self._history else 0.0
        }
    
    def observation(self) -> Observation:
        """
        Return AGENT OBSERVATION (what agent sees).
        Per OpenEnv spec: broken_sql, schema, sample_data, hints.
        """
        if not self._current_scenario_id:
            raise RuntimeError("Environment not reset. Call reset() first.")
        
        scenario = get_scenario(self._current_scenario_id)
        with sandbox_db() as db:
            db.execute_script(scenario.setup_sql)
            obs = self._build_observation(db, scenario, None)
            obs.step_count = self._step_count
            return obs
    
    def _build_observation(self, db, scenario, error_msg: Optional[str]) -> Observation:
        """Construct observation from database state"""
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
            "task_id": self._current_scenario_id,
            "total_steps": self._step_count,
            "total_reward": round(total_reward, 4),
            "average_score": round(avg_score, 2),
            "history": self._history,
            "done": self._done
        }


# Global environment instance
_env_instance: Optional[SQLMigrationEnv] = None

def get_env() -> SQLMigrationEnv:
    """Get or create global environment instance"""
    global _env_instance
    if _env_instance is None:
        _env_instance = SQLMigrationEnv()
    return _env_instance
