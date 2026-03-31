import sqlite3
from typing import Any, Dict, List, Optional
from environment.models import Observation, StepResult
from environment.tasks import TASKS
from environment.graders import grade

class SQLMigrationEnv:
    def __init__(self):
        self.conn: Optional[sqlite3.Connection] = None
        self.current_task_id: Optional[str] = None
        self.done = False

    def reset(self, task_id: str) -> Observation:
        if task_id not in TASKS:
            raise ValueError(f"Task {task_id} not found.")

        self.current_task_id = task_id
        self.done = False
        task = TASKS[task_id]

        # Reset DB (for observation generation, though grader handles it independently)
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        # Setup schema context
        try:
            self.conn.executescript(task["schema_context"])
            if task.get("seed_sql"):
                self.conn.executescript(task["seed_sql"])
            self.conn.commit()
        except Exception as e:
            print(f"Error initializing schema context: {e}")

        return Observation(
            task_id=task_id,
            pr_title=task["pr_title"],
            broken_sql=task["broken_sql"],
            schema=task["schema_context"],
            seed_data=task["seed_data"],
            task_description=task["task_description"]
        )

    def step(self, fixed_sql: str) -> StepResult:
        if not self.current_task_id:
            raise RuntimeError("Env must be reset before step()")

        # 1. Use the spec grader
        result = grade(self.current_task_id, fixed_sql)
        reward_value = result["score"]
        
        self.done = True
        
        # 2. Re-gen observation for state after migration (as per typical RL flow)
        obs = self.reset(self.current_task_id)
        
        return StepResult(
            observation=obs,
            reward=reward_value,
            done=True,
            info={
                "breakdown": result.get("breakdown"),
                "passed": result.get("passed"),
                "error": result.get("error")
            }
        )

    def state(self) -> Dict[str, Any]:
        return {
            "task_id": self.current_task_id,
            "done": self.done,
            "db_active": self.conn is not None
        }
