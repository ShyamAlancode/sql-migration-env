"""
inference.py — SQL Migration Safety Gym
========================================
OpenEnv Hackathon 2026 — MANDATORY SUBMISSION FILE

STDOUT FORMAT (STRICTLY ENFORCED BY AUTOMATED EVALUATOR):
    [START] task=<task_name> env=sql-migration-env model=<model_name>
    [STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
    [END]   success=<true|false> steps=<n> rewards=<r1,r2,...,rn>

ENVIRONMENT VARIABLES:
    API_BASE_URL   — LLM API endpoint (default: Groq)
    MODEL_NAME     — Model identifier (default: llama-3.1-8b-instant)
    HF_TOKEN       — Hugging Face / API key
    OPENAI_API_KEY — OpenAI-compatible API key (falls back to HF_TOKEN)
    ENV_URL        — URL of the running environment (default: localhost:7860)
"""

import os
import sys
import json
import time
import requests
from typing import Optional, Dict, Any, List

from openai import OpenAI


# ============================================================================
# ENVIRONMENT VARIABLES (per OpenEnv mandatory spec)
# ============================================================================
API_BASE_URL   = os.environ.get("API_BASE_URL",    "https://api.groq.com/openai/v1")
MODEL_NAME     = os.environ.get("MODEL_NAME",      "llama-3.1-8b-instant")
HF_TOKEN       = os.environ.get("HF_TOKEN",        "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY",  HF_TOKEN)
ENV_URL        = os.environ.get("ENV_URL",         "http://localhost:7860")

BENCHMARK      = "sql-migration-env"
MAX_STEPS      = 3   # Keep under 20min on 2vCPU / 8GB RAM
TASKS          = ["easy", "medium", "hard"]
SUCCESS_THRESHOLD = 0.7

# ============================================================================
# MANDATORY STDOUT FORMAT HELPERS
# ============================================================================

def log_start(task: str, env: str, model: str) -> None:
    """Emit [START] line — MANDATORY FORMAT."""
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    """Emit [STEP] line — MANDATORY FORMAT."""
    error_val = error if error else "null"
    done_val  = str(done).lower()
    # Sanitize action — remove newlines, truncate to 100 chars, no repr quotes
    action_safe = action.replace("\n", " ").replace("\r", "").replace("\t", " ").strip()[:100]
    print(
        f"[STEP] step={step} action={action_safe} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    """Emit [END] line — MANDATORY FORMAT."""
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


# ============================================================================
# SYSTEM PROMPT — Expert-level SQLite migration engineer
# ============================================================================

SYSTEM_PROMPT = """You are an expert Database Migration Engineer specializing in SQLite.
Fix broken SQL migration scripts before they corrupt production databases.

SQLITE-SPECIFIC RULES (CRITICAL):
1. SQLite LIMITED ALTER TABLE support:
   - Cannot add UNIQUE/FK/CHECK constraints via ALTER TABLE
   - Use: CREATE UNIQUE INDEX idx ON table(col)
   - NOT NULL columns need: DEFAULT 'value'
   - Each ALTER TABLE must be a separate statement

2. SILENT CORRUPTION patterns to detect (HARD mode):
   - UPDATE without WHERE clause → corrupts ALL rows
   - INSERT...SELECT with wrong column order → scrambles data
   - Type cast (REAL → INTEGER) truncates decimals silently
   - ALTER + immediate UPDATE reads DEFAULT not populated values (execution order bug)

3. For complex schema changes: use table-rebuild pattern:
   BEGIN TRANSACTION;
   CREATE TABLE new_t (...);
   INSERT INTO new_t SELECT ... FROM old_t;
   DROP TABLE old_t;
   ALTER TABLE new_t RENAME TO old_t;
   COMMIT;

RESPOND WITH VALID JSON ONLY:
{
    "fixed_sql": "the corrected SQLite migration script",
    "explanation": "brief explanation of the bug and fix",
    "confidence": 0.9
}"""


# ============================================================================
# AGENT
# ============================================================================

class SQLMigrationAgent:
    """OpenAI-client-based agent for SQL Migration Safety Gym."""

    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY, base_url=API_BASE_URL)

    def _format_obs(self, obs: Dict[str, Any]) -> str:
        """Format observation into a compact prompt."""
        lines = [
            "=== BROKEN MIGRATION ===",
            obs.get("broken_sql", "(none)"),
            "",
            f"Difficulty: {obs.get('difficulty', 'unknown')}",
            f"Step: {obs.get('step_count', 0)}/{obs.get('max_steps', 3)}",
        ]

        if obs.get("error_message"):
            lines += ["", "=== ERROR ===", obs["error_message"]]
        else:
            lines += ["", "=== STATUS ===", "No error — check for SILENT CORRUPTION"]

        schema = obs.get("current_schema")
        if schema:
            lines += ["", f"=== TABLE: {schema.get('table_name', '?')} ==="]
            for col in schema.get("columns", []):
                nn = "NOT NULL" if col.get("notnull") else "NULL"
                lines.append(f"  {col.get('name')} {col.get('type')} {nn}")

        if obs.get("sample_data"):
            lines += ["", "=== SAMPLE DATA ===", json.dumps(obs["sample_data"][:3], indent=2)]

        if obs.get("hint"):
            lines += ["", f"[HINT] {obs['hint']}"]

        lines.append("\nRespond with JSON only.")
        return "\n".join(lines)

    def get_action(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self._format_obs(obs)
        try:
            resp = self.client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.1,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or "{}"
            data = json.loads(content)
            return {
                "fixed_sql":   data.get("fixed_sql", "SELECT 1;").strip(),
                "explanation": data.get("explanation", "").strip()[:500],
                "confidence":  float(data.get("confidence", 0.5)),
            }
        except Exception as exc:
            print(f"[DEBUG] LLM error: {exc}", file=sys.stderr, flush=True)
            return {"fixed_sql": "SELECT 1;", "explanation": "LLM error", "confidence": 0.0}


# ============================================================================
# EPISODE RUNNER
# ============================================================================

def run_episode(agent: SQLMigrationAgent, task_id: str) -> Dict[str, Any]:
    """
    Run one episode for a given task_id.
    Emits [START], [STEP]×n, [END] to stdout.
    Returns episode summary dict.
    """
    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False
    error_msg = None

    try:
        # RESET
        reset_resp = requests.post(
            f"{ENV_URL}/reset",
            json={"task_id": task_id},
            timeout=30,
        )
        reset_resp.raise_for_status()
        reset_data = reset_resp.json()
        # SPEC: /reset returns {observation: {...}, done: false, reward: null}
        obs = reset_data.get("observation", reset_data)  # graceful fallback for old flat format

        for step in range(1, MAX_STEPS + 1):
            # Get action from LLM
            action = agent.get_action(obs)
            error_msg = None

            # STEP
            try:
                step_resp = requests.post(
                    f"{ENV_URL}/step",
                    json={
                        "fixed_sql":   action["fixed_sql"],
                        "explanation": action["explanation"],
                        "confidence":  action["confidence"],
                    },
                    timeout=30,
                )
                step_resp.raise_for_status()
                result = step_resp.json()
            except Exception as e:
                error_msg = str(e)[:80]
                log_step(step=step, action=action["fixed_sql"], reward=0.0, done=True, error=error_msg)
                rewards.append(0.0)
                steps_taken = step
                break

            # Parse result
            reward = float(result.get("reward", 0.0))
            done   = bool(result.get("done", False))
            obs    = result.get("observation", obs)
            info   = result.get("info", {})

            # Capture any grader error
            grading = info.get("grading_result", {})
            if not grading.get("syntax_correct", True):
                error_msg = grading.get("detailed_feedback", None)
                if error_msg:
                    error_msg = error_msg[:80]

            rewards.append(reward)
            steps_taken = step

            # Emit mandatory STEP log
            log_step(step=step, action=action["fixed_sql"], reward=reward, done=done, error=error_msg)

            if done:
                break

        score = max(rewards) if rewards else 0.0  # best step reward, already 0-1
        success = score >= SUCCESS_THRESHOLD

    except Exception as exc:
        error_msg = str(exc)[:80]
        print(f"[DEBUG] Episode error: {exc}", file=sys.stderr, flush=True)
        if not rewards:
            rewards = [0.0]
        score = 0.0

    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    return {
        "task": task_id,
        "score": score,
        "steps": steps_taken,
        "success": success,
    }


# ============================================================================
# MAIN — Run all 3 mandatory tasks
# ============================================================================

def main():
    agent = SQLMigrationAgent()
    results = {}

    for task_id in TASKS:
        summary = run_episode(agent, task_id)
        results[task_id] = summary.get("score", 0.0)
        # Brief pause between episodes
        time.sleep(1)

    # Final summary to stderr (NOT stdout — stdout is reserved for [START]/[STEP]/[END])
    print(
        json.dumps({"model": MODEL_NAME, "environment": BENCHMARK, "scores": results}),
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    main()