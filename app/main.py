"""
FastAPI server for SQL Migration Safety Gym
OpenEnv Hackathon 2026 - Spec Compliant Version
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from typing import Optional
from pydantic import BaseModel
import os

from app.models import Action, Observation, DifficultyLevel, GradingResult
from app.environment import SQLMigrationEnv, get_env
from app.scenarios import ALL_SCENARIOS


# Request/Response models
class ResetRequest(BaseModel):
    task_id: Optional[str] = None      # Primary: spec-compliant
    scenario_id: Optional[str] = None  # Backward compatibility
    difficulty: Optional[str] = None   # Alternative

class StepRequest(BaseModel):
    fixed_sql: str
    explanation: Optional[str] = ""
    confidence: Optional[float] = 0.5

class StepResponse(BaseModel):
    observation: Observation
    reward: float
    done: bool
    info: dict


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    print("🚀 Starting SQL Migration Safety Gym server...")
    env = get_env()
    print(f"✅ Environment ready with {len(ALL_SCENARIOS)} scenarios")
    yield
    print("🛑 Shutting down server...")


app = FastAPI(
    title="SQL Migration Safety Gym",
    description=(
        "Production-grade OpenEnv environment for training and evaluating "
        "AI agents on database migration safety. Implements cryptographic "
        "state verification, silent corruption detection, and RFC 001/002/003 compliance."
    ),
    version="1.0.0",
    contact={
        "name": "SQL Migration Safety Support",
        "url": "https://huggingface.co/spaces/ShyamAlancode/sql-migration-env"
    },
    lifespan=lifespan
)

# Add after app creation
# Create static directory if not exists
os.makedirs("static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/ui")
async def web_interface():
    """Interactive web UI for demo"""
    return FileResponse("static/index.html")

@app.get("/")
async def root():
    """Redirect to UI"""
    return {"message": "SQL Migration Safety Gym", "ui": "/ui", "docs": "/docs"}

# CORS for HF Spaces
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint for HF Spaces"""
    return {
        "status": "healthy",
        "scenarios_available": len(ALL_SCENARIOS),
        "difficulties": ["easy", "medium", "hard"],
        "version": "1.0.0"
    }


@app.get("/scenarios")
async def list_scenarios(difficulty: Optional[str] = None):
    """List available migration scenarios"""
    scenarios = list(ALL_SCENARIOS.values())
    if difficulty:
        scenarios = [s for s in scenarios if s.difficulty.value == difficulty]
    
    return {
        "count": len(scenarios),
        "scenarios": [
            {
                "id": s.id,
                "difficulty": s.difficulty.value,
                "description": s.description,
                "is_silent_corruption": s.is_silent_corruption
            }
            for s in scenarios
        ]
    }


@app.get("/tasks")
async def list_tasks():
    """Alias for /scenarios - OpenEnv spec compliance"""
    return await list_scenarios()


@app.post("/reset", 
          summary="Reset SQL Environment",
          description="Initializes the SQL sandbox for a given task_id (easy/medium/hard) or specific scenario_id. Returns the initial observation.")
async def reset_environment(request: ResetRequest):
    """
    Reset environment to initial state.
    Accepts task_id (easy/medium/hard) per OpenEnv spec.
    """
    env = get_env()
    
    # Priority: task_id > scenario_id > difficulty
    diff_enum = None
    effective_scenario_id = request.scenario_id
    
    if request.task_id:
        # task_id is difficulty level: easy, medium, hard
        try:
            diff_enum = DifficultyLevel(request.task_id.lower())
        except ValueError:
            # If not a valid difficulty, treat as scenario_id
            effective_scenario_id = request.task_id
    elif request.difficulty:
        try:
            diff_enum = DifficultyLevel(request.difficulty.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid difficulty: {request.difficulty}")
    
    try:
        obs = env.reset(scenario_id=effective_scenario_id, difficulty=diff_enum)
        return obs
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


@app.post("/step", 
          summary="Apply Migration Fix",
          response_model=StepResponse,
          description="Executes a multi-statement SQL migration against the sandbox, grades the result, and returns rewards/observations.")
async def step_environment(request: StepRequest):
    """Execute one step in the environment"""
    env = get_env()
    
    action = Action(
        fixed_sql=request.fixed_sql,
        explanation=request.explanation or "",
        confidence=request.confidence or 0.5
    )
    
    try:
        obs, reward, done, info = env.step(action)
        # SPEC COMPLIANCE: Normalize reward from 0-100 to 0.0-1.0
        reward_normalized = round(reward / 100.0, 4)
        return StepResponse(
            observation=obs,
            reward=reward_normalized,
            done=done,
            info=info
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Step failed: {str(e)}")


@app.get("/state",
         summary="Get Internal State",
         description="Returns the full internal state of the current episode, including history and step counts. Hidden from agents.")
async def get_current_state():
    """
    Get current INTERNAL STATE (not observation).
    Returns: episode_id, step_count, done, history, etc.
    """
    env = get_env()
    try:
        return env.state()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/observation",
         summary="Get Agent Observation",
         description="Returns only the signal visible to the agent: schema, sample data, and hints.")
async def get_current_observation():
    """
    Get current AGENT OBSERVATION (what agent sees).
    Returns: broken_sql, schema, sample_data, hints.
    """
    env = get_env()
    try:
        return env.observation()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/stats")
async def get_episode_stats():
    """Get statistics for current episode"""
    env = get_env()
    stats = env.get_episode_stats()
    if not stats:
        raise HTTPException(status_code=404, detail="No active episode. Call /reset first.")
    return stats


@app.get("/metrics",
         summary="Prometheus Metrics",
         description="Returns environment metrics in a format compatible with production monitoring tools.")
async def get_metrics():
    """Prometheus-compatible metrics for production monitoring"""
    env = get_env()
    state = env.state()
    
    return {
        "openenv_steps_total": state.get("step_count", 0),
        "openenv_episodes_total": 1 if state.get("episode_id") else 0,
        "openenv_active_sessions": 1 if not state.get("done", True) else 0,
        "openenv_errors_total": 0,  # Track if you add error counting
        "scenarios_available": len(ALL_SCENARIOS),
        "version": "1.0.0"
    }


@app.get("/spec")
async def spec_compliance():
    """Verify OpenEnv API compliance"""
    return {
        "api_version": "openenv-v1",
        "endpoints": {
            "reset": "/reset (POST)",
            "step": "/step (POST)",
            "state": "/state (GET)",
            "observation": "/observation (GET)",
            "tasks": "/tasks (GET)",
            "metrics": "/metrics (GET)"
        },
        "environment": "SQLMigrationEnv",
        "observation_space": "Observation (Pydantic)",
        "action_space": "Action (Pydantic)",
        "reward_range": [0.0, 1.1],
        "max_episode_steps": 5,
        "compliance": "RFC 001, 002, 003"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
