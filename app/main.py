"""
FastAPI server for SQL Migration Safety Gym
OpenEnv Hackathon 2026 - Spec Compliant Version
Session-based concurrency: each X-Session-ID gets its own SQLMigrationEnv instance.
Falls back to global singleton if no header provided (backward compat).
"""

from fastapi import FastAPI, HTTPException, Header, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from typing import Optional
from pydantic import BaseModel
import os
import uuid

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


# ── Session Registry ──────────────────────────────────────────────────────────
# Maps session_id → SQLMigrationEnv instance
_session_registry: dict[str, SQLMigrationEnv] = {}

def get_session_env(session_id: Optional[str]) -> SQLMigrationEnv:
    """
    Return the env for the given session_id, or the global singleton if None.
    Creates a new per-session env on first access.
    """
    if not session_id:
        return get_env()  # backward-compat: global singleton
    if session_id not in _session_registry:
        _session_registry[session_id] = SQLMigrationEnv()
    return _session_registry[session_id]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    print("Starting SQL Migration Safety Gym server...")
    env = get_env()
    print(f"Environment ready with {len(ALL_SCENARIOS)} scenarios")
    yield
    print("Shutting down server...")


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
    expose_headers=["X-Session-ID"],
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


class ResetResponse(BaseModel):
    """OpenEnv-spec reset response: nested observation + done + reward"""
    observation: Observation
    done: bool = False
    reward: Optional[float] = None


@app.post("/reset",
          summary="Reset SQL Environment",
          response_model=ResetResponse,
          description=(
              "Initializes the SQL sandbox for a given task_id (easy/medium/hard) or specific "
              "scenario_id. Returns the OpenEnv-spec response: {observation, done, reward}. "
              "Optionally provide X-Session-ID header for isolated concurrent sessions."
          ))
async def reset_environment(
    response: Response,
    request: ResetRequest = ResetRequest(),
    x_session_id: Optional[str] = Header(default=None)
):
    """
    Reset environment to initial state.
    Returns official OpenEnv structure: {"observation": {...}, "done": false, "reward": null}
    - If X-Session-ID header provided: uses/creates a per-session env.
    - If absent: falls back to global singleton (backward compat).
    """
    session_id = x_session_id or str(uuid.uuid4())
    env = get_session_env(session_id)

    # Priority: task_id > scenario_id > difficulty
    diff_enum = None
    effective_scenario_id = request.scenario_id

    if request.task_id:
        try:
            diff_enum = DifficultyLevel(request.task_id.lower())
        except ValueError:
            effective_scenario_id = request.task_id
    elif request.difficulty:
        try:
            diff_enum = DifficultyLevel(request.difficulty.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid difficulty: {request.difficulty}")

    try:
        obs = env.reset(scenario_id=effective_scenario_id, difficulty=diff_enum)
        response.headers["X-Session-ID"] = session_id
        # SPEC COMPLIANCE: return nested {observation, done, reward} — required by EnvClient
        return ResetResponse(observation=obs, done=False, reward=None)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


@app.post("/step", 
          summary="Apply Migration Fix",
          response_model=StepResponse,
          description=(
              "Executes a multi-statement SQL migration against the sandbox, grades the result, "
              "and returns rewards/observations. Provide X-Session-ID to route to your session. "
              "Falls back to global singleton if header absent."
          ))
async def step_environment(
    request: StepRequest,
    x_session_id: Optional[str] = Header(default=None)
):
    """Execute one step in the environment"""
    env = get_session_env(x_session_id)
    
    action = Action(
        fixed_sql=request.fixed_sql,
        explanation=request.explanation or "",
        confidence=request.confidence or 0.5
    )
    
    try:
        obs, reward, done, info = env.step(action)
        # Environment already normalizes to 0.0-1.0; no need for redundant division
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


@app.get("/state",
         summary="Get Internal State",
         description="Returns the full internal state of the current episode, including history and step counts. Hidden from agents.")
async def get_current_state(x_session_id: Optional[str] = Header(default=None)):
    """
    Get current INTERNAL STATE (not observation).
    Returns: episode_id, step_count, done, history, etc.
    """
    env = get_session_env(x_session_id)
    try:
        return env.state()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/observation",
         summary="Get Agent Observation",
         description="Returns only the signal visible to the agent: schema, sample data, and hints.")
async def get_current_observation(x_session_id: Optional[str] = Header(default=None)):
    """
    Get current AGENT OBSERVATION (what agent sees).
    Returns: broken_sql, schema, sample_data, hints.
    """
    env = get_session_env(x_session_id)
    try:
        return env.observation()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/stats")
async def get_episode_stats(x_session_id: Optional[str] = Header(default=None)):
    """Get statistics for current episode"""
    env = get_session_env(x_session_id)
    stats = env.get_episode_stats()
    if not stats:
        raise HTTPException(status_code=404, detail="No active episode. Call /reset first.")
    return stats


@app.get("/metrics",
         summary="Prometheus Metrics",
         description="Returns environment metrics in a format compatible with production monitoring tools.")
async def get_metrics(x_session_id: Optional[str] = Header(default=None)):
    """Prometheus-compatible metrics for production monitoring"""
    env = get_session_env(x_session_id)
    state = env.state()
    
    return {
        "openenv_steps_total": state.get("step_count", 0),
        "openenv_episodes_total": 1 if state.get("episode_id") else 0,
        "openenv_active_sessions": len(_session_registry),
        "openenv_errors_total": 0,
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
        "reward_range": [0.0, 1.0],
        "max_episode_steps": 5,
        "compliance": "RFC 001, 002, 003",
        "concurrency": "Session-isolated via X-Session-ID header"
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for OpenEnv client persistent connections.
    """
    await websocket.accept()
    session_id = str(uuid.uuid4())
    env = get_session_env(session_id)
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            msg_data = data.get("data", {})
            
            try:
                if msg_type == "reset":
                    task_id = msg_data.get("task_id")
                    scenario_id = msg_data.get("scenario_id")
                    difficulty_str = msg_data.get("difficulty")
                    
                    diff_enum = None
                    effective_scenario_id = scenario_id
                    if task_id:
                        try:
                            diff_enum = DifficultyLevel(task_id.lower())
                        except ValueError:
                            effective_scenario_id = task_id
                    elif difficulty_str:
                        diff_enum = DifficultyLevel(difficulty_str.lower())
                        
                    obs = env.reset(scenario_id=effective_scenario_id, difficulty=diff_enum)
                    await websocket.send_json({
                        "type": "reset_response",
                        "data": {
                            "obs": obs.model_dump(),
                            "done": False,
                            "reward": 0.0,
                            "info": {}
                        }
                    })
                    
                elif msg_type == "step":
                    action = Action(
                        fixed_sql=msg_data.get("fixed_sql", ""),
                        explanation=msg_data.get("explanation", ""),
                        confidence=msg_data.get("confidence", 0.5)
                    )
                    obs, reward, done, info = env.step(action)
                    await websocket.send_json({
                        "type": "step_response",
                        "data": {
                            "obs": obs.model_dump(),
                            "reward": reward,
                            "done": done,
                            "info": info
                        }
                    })
                    
                elif msg_type == "state":
                    state_data = env.state()
                    await websocket.send_json({
                        "type": "state_response",
                        "data": state_data
                    })
                    
                else:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": f"Unknown message type: {msg_type}", "code": 400}
                    })
                    
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": str(e), "code": 500}
                })
                
    except WebSocketDisconnect:
        # Cleanup if needed
        if session_id in _session_registry:
            del _session_registry[session_id]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
