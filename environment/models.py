from pydantic import BaseModel
from typing import Any, Dict, Optional, List

class Observation(BaseModel):
    task_id: str
    pr_title: str
    broken_sql: str
    schema: str
    seed_data: List[Dict[str, Any]]
    task_description: str

class Action(BaseModel):
    fixed_sql: str

class Reward(BaseModel):
    value: float
    reason: str

class StepResult(BaseModel):
    observation: Observation
    reward: float
    done: bool
    info: Dict[str, Any]
