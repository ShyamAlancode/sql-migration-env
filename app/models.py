"""
Pydantic models for sql-migration-env
OpenEnv Hackathon 2026
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Optional, List, Dict, Any
from enum import Enum


class DifficultyLevel(str, Enum):
    EASY = "easy"      # Syntax errors
    MEDIUM = "medium"  # Constraint violations
    HARD = "hard"      # Silent data corruption


class Action(BaseModel):
    """Agent's proposed action to fix the migration"""
    model_config = ConfigDict(strict=False)
    
    fixed_sql: str = Field(
        ..., 
        description="The corrected SQL migration script",
        examples=["ALTER TABLE users ADD COLUMN email VARCHAR(255) NOT NULL DEFAULT '';"]
    )
    explanation: str = Field(
        default="",
        description="Explanation of changes made",
        max_length=1000
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Agent's confidence in the fix"
    )


class SchemaInfo(BaseModel):
    """Current database schema state"""
    table_name: str
    columns: List[Dict[str, Any]]  # name, type, nullable, default
    indexes: List[Dict[str, Any]]
    foreign_keys: List[Dict[str, Any]]


class Observation(BaseModel):
    """What the agent observes"""
    model_config = ConfigDict(strict=False)
    
    scenario_id: str
    difficulty: DifficultyLevel
    description: str = Field(..., description="Task description and requirements")
    broken_sql: str = Field(..., description="The buggy migration script")
    error_message: Optional[str] = Field(
        default=None, 
        description="Error from running broken SQL (None for silent corruption)"
    )
    current_schema: Optional[SchemaInfo] = None
    previous_schema: Optional[SchemaInfo] = None
    sample_data: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Sample rows from affected table (first 5 rows)"
    )
    hint: Optional[str] = Field(
        default=None,
        description="Optional hint for easy mode"
    )
    step_count: int = Field(default=0, ge=0)
    max_steps: int = Field(default=5, ge=1)


class GradingResult(BaseModel):
    """Detailed scoring breakdown with component scores"""
    model_config = ConfigDict(strict=True)
    
    total_score: float = Field(ge=0, le=100)
    syntax_correct: bool
    syntax_score: float  # 0-20
    
    data_integrity_score: float  # 0-40
    schema_correct_score: float  # 0-30
    efficiency_score: float  # 0-10
    
    # NEW: Detailed breakdown for agent learning
    breakdown: Dict[str, float] = Field(default_factory=dict)
    
    detailed_feedback: str
    silent_corruption_detected: Optional[bool] = None
    
    def __init__(self, **data):
        super().__init__(**data)
        # Auto-populate breakdown
        self.breakdown = {
            "syntax": round(self.syntax_score, 2),
            "data_integrity": round(self.data_integrity_score, 2),
            "schema": round(self.schema_correct_score, 2),
            "efficiency": round(self.efficiency_score, 2),
            "total": round(self.total_score, 2)
        }


class State(BaseModel):
    """Internal environment state"""
    model_config = ConfigDict(strict=False)
    
    scenario_id: str
    difficulty: DifficultyLevel
    original_sql: str
    current_sql: str  # After agent modifications
    db_state_hash: str  # For detecting corruption
    step_count: int
    done: bool
    history: List[Dict[str, Any]] = []  # Previous actions


class MigrationScenario(BaseModel):
    """Test case definition"""
    model_config = ConfigDict(strict=False)
    
    id: str
    difficulty: DifficultyLevel
    description: str
    
    # Setup
    setup_sql: str  # SQL to create initial schema/populate data
    
    # The buggy migration
    broken_migration: str
    
    # Expected outcome
    expected_schema: Optional[SchemaInfo] = None
    
    # For grading
    validation_queries: List[str]  # Queries to verify data integrity
    expected_results: List[List[Dict[str, Any]]]  # Expected query results
    
    # Hint for easy mode
    hint: Optional[str] = None
    
    # Is this a silent corruption case?
    is_silent_corruption: bool = False
