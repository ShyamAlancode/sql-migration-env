"""
FastAPI server for SQL Migration Safety Gym
Exposes OpenEnv API over HTTP for HF Spaces deployment
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Optional
from pydantic import BaseModel

from app.models import Action, Observation, DifficultyLevel
from app.environment import SQLMigrationEnv, get_env
from app.scenarios import ALL_SCENARIOS


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    print("Starting SQL Migration Safety Gym server...")
    # Initialize environment
    env = get_env()
    print(f"Environment ready with {len(ALL_SCENARIOS)} scenarios")
    yield
    print("Shutting down server...")


app = FastAPI(
    title="SQL Migration Safety Gym",
    description="OpenEnv environment for training AI agents to fix SQL migrations",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for HF Spaces and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # HF Spaces requirement
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response models for API
class ResetRequest(BaseModel):
    scenario_id: Optional[str] = None
    difficulty: Optional[str] = None

class StepRequest(BaseModel):
    fixed_sql: str
    explanation: Optional[str] = ""
    confidence: Optional[float] = 0.5

class StepResponse(BaseModel):
    observation: Observation
    reward: float
    done: bool
    info: dict

class EpisodeStats(BaseModel):
    episode_id: str
    scenario_id: str
    total_steps: int
    total_reward: float
    average_score: float
    done: bool


from fastapi.responses import RedirectResponse

@app.get("/")
async def root():
    """Redirect to API documentation"""
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health_check():
    """Health check endpoint for HF Spaces"""
    return {
        "status": "healthy",
        "scenarios_available": len(ALL_SCENARIOS),
        "difficulties": ["easy", "medium", "hard"]
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


@app.post("/reset", response_model=Observation)
async def reset_environment(request: ResetRequest):
    """
    Reset environment to initial state.
    
    If scenario_id provided, loads that specific scenario.
    If difficulty provided, randomly selects from that difficulty.
    Otherwise, random scenario from all difficulties.
    """
    env = get_env()
    
    diff_enum = None
    if request.difficulty:
        try:
            diff_enum = DifficultyLevel(request.difficulty.lower())
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid difficulty: {request.difficulty}. Use: easy, medium, hard"
            )
    
    try:
        obs = env.reset(scenario_id=request.scenario_id, difficulty=diff_enum)
        return obs
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


@app.post("/step", response_model=StepResponse)
async def step_environment(request: StepRequest):
    """
    Execute one step in the environment.
    
    Agent provides fixed SQL and receives observation, reward, and done flag.
    """
    env = get_env()
    
    action = Action(
        fixed_sql=request.fixed_sql,
        explanation=request.explanation or "",
        confidence=request.confidence or 0.5
    )
    
    try:
        obs, reward, done, info = env.step(action)
        return StepResponse(
            observation=obs,
            reward=reward,
            done=done,
            info=info
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Step failed: {str(e)}")


@app.get("/state", response_model=Observation)
async def get_current_state():
    """Get current observation without taking a step"""
    env = get_env()
    try:
        return env.state()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/stats", response_model=EpisodeStats)
async def get_episode_stats():
    """Get statistics for current episode"""
    env = get_env()
    stats = env.get_episode_stats()
    if not stats:
        raise HTTPException(status_code=404, detail="No active episode. Call /reset first.")
    return EpisodeStats(**stats)


# OpenEnv spec compliance verification endpoint
@app.get("/spec")
async def spec_compliance():
    """Verify OpenEnv API compliance"""
    return {
        "api_version": "openenv-v1",
        "endpoints": {
            "reset": "/reset (POST)",
            "step": "/step (POST)", 
            "state": "/state (GET)"
        },
        "environment": "SQLMigrationEnv",
        "observation_space": "Observation (Pydantic)",
        "action_space": "Action (Pydantic)",
        "reward_range": [0.0, 1.1],  # 0-1 + bonus
        "max_episode_steps": 5
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)  # HF Spaces default port
