import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from environment.env import SQLMigrationEnv
from environment.models import Observation, Action, StepResult
import os

app = FastAPI(title="SQL Migration Safety Gym")
env = SQLMigrationEnv()

class ResetRequest(BaseModel):
    task_id: str

class StepRequest(BaseModel):
    fixed_sql: str

@app.post("/reset", response_model=Observation)
async def reset(req: ResetRequest):
    try:
        obs = env.reset(req.task_id)
        return obs
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/step", response_model=StepResult)
async def step(req: StepRequest):
    try:
        result = env.step(req.fixed_sql)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/state")
async def get_state():
    return env.state()

@app.get("/health")
async def health():
    return {"status": "ok", "env": "sql-migration-env"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
