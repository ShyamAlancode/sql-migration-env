"""
Inference script for SQL Migration Safety Gym
OpenEnv Hackathon 2026 - SPEC COMPLIANT VERSION
REQUIRED FILE - Disqualification if missing or broken
"""

import os
import sys
import json
import time
import requests
from typing import Optional, Dict, Any, List
from openai import OpenAI


# REQUIRED ENVIRONMENT VARIABLES (exact names per OpenEnv spec)
API_BASE_URL = os.environ.get("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4o-mini")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", HF_TOKEN)  # Fallback to HF_TOKEN
ENV_URL = os.environ.get("ENV_URL", "http://localhost:7860")


class SQLMigrationAgent:
    """
    AI Agent for fixing SQL migration scripts.
    COMPLIANT with OpenEnv Hackathon spec.
    Uses OpenAI client with configurable base_url for Groq/HF/Local.
    """
    
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        env_url: Optional[str] = None
    ):
        self.model = model or MODEL_NAME
        self.env_url = env_url or ENV_URL
        
        # Initialize OpenAI client with compliant env vars
        self.client = OpenAI(
            api_key=api_key or OPENAI_API_KEY,
            base_url=base_url or API_BASE_URL
        )
        
        self.system_prompt = """You are an expert Database Migration Engineer specializing in SQLite.
Your task is to review broken SQL migration scripts and fix them before they corrupt production databases.

SQLITE-SPECIFIC RULES (CRITICAL):
1. SQLite has LIMITED ALTER TABLE support:
   - Cannot add UNIQUE constraints directly: ❌ ALTER TABLE ... ADD CONSTRAINT UNIQUE
   - Instead use: ✅ CREATE UNIQUE INDEX index_name ON table(column)
   - Cannot add FOREIGN KEY constraints to existing tables
   - Cannot add CHECK constraints to existing tables
   
2. For NOT NULL columns on existing tables:
   - Must provide DEFAULT value: ALTER TABLE ... ADD COLUMN col TYPE NOT NULL DEFAULT 'value'

3. For UNIQUE constraints on tables with duplicates:
   - Clean data first, OR use CREATE UNIQUE INDEX (SQLite allows this)

4. Each ALTER TABLE statement must be separate (semicolon required)

CRITICAL RULES:
1. Preserve ALL existing data - never lose rows
2. Watch for SILENT CORRUPTION (HARD mode):
   - UPDATE without WHERE updates ALL rows
   - Column misalignment in INSERT...SELECT scrambles data
   - Wrong defaults overwrite historical data

RESPOND WITH JSON:
{
    "fixed_sql": "The corrected SQLite migration script",
    "explanation": "Brief explanation of what was wrong and how you fixed it",
    "confidence": 0.95
}

Be careful. Be precise. Check your work."""
        
    def run_episode(
        self,
        task_id: Optional[str] = None,
        difficulty: Optional[str] = None,
        max_steps: int = 5,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Run one full episode.
        
        Args:
            task_id: Task identifier (easy/medium/hard) per OpenEnv spec
            difficulty: Alternative difficulty specification
        """
        # Map task_id to difficulty
        effective_difficulty = task_id or difficulty or "easy"
        
        if verbose:
            print(f"🚀 Starting episode with model: {self.model}")
            print(f"   Task/Difficulty: {effective_difficulty}")
        
        # Reset environment using task_id per spec
        reset_payload = {}
        if task_id:
            reset_payload["task_id"] = task_id
        if difficulty:
            reset_payload["difficulty"] = difficulty
            
        try:
            response = requests.post(f"{self.env_url}/reset", json=reset_payload, timeout=30)
            response.raise_for_status()
            obs_data = response.json()
        except Exception as e:
            print(f"❌ Environment reset failed: {e}")
            return {"error": str(e), "history": []}
        
        scenario_id = obs_data.get("scenario_id", "unknown")
        actual_difficulty = obs_data.get("difficulty", "unknown")
        
        if verbose:
            print(f"   Loaded scenario: {scenario_id} ({actual_difficulty})")
        
        history = []
        total_reward = 0.0
        
        for step in range(max_steps):
            if verbose:
                print(f"\n--- Step {step + 1}/{max_steps} ---")
            
            # Get action from LLM
            action = self._get_action(obs_data)
            
            if verbose:
                print(f"📝 Action: {action.get('explanation', '')[:100]}...")
                print(f"🔧 SQL: {action.get('fixed_sql', '')[:80]}...")
            
            # Execute step
            try:
                step_response = requests.post(
                    f"{self.env_url}/step",
                    json={
                        "fixed_sql": action.get("fixed_sql", ""),
                        "explanation": action.get("explanation", ""),
                        "confidence": action.get("confidence", 0.5)
                    },
                    timeout=30
                )
                step_response.raise_for_status()
                result = step_response.json()
            except Exception as e:
                print(f"❌ Step failed: {e}")
                break
            
            obs_data = result.get("observation", obs_data)
            reward = result.get("reward", 0.0)
            done = result.get("done", False)
            info = result.get("info", {})
            
            total_reward += reward
            
            history.append({
                "step": step + 1,
                "action": action,
                "reward": reward,
                "grading": info.get("grading_result", {}),
                "done": done
            })
            
            if verbose:
                print(f"⭐ Reward: {reward:.3f} | Done: {done}")
                if info.get("grading_result"):
                    gr = info["grading_result"]
                    print(f"   Score: {gr.get('total_score', 0):.1f}/100")
            
            if done:
                if verbose:
                    print(f"\n✅ Episode complete!")
                break
        
        return {
            "model": self.model,
            "scenario_id": scenario_id,
            "difficulty": actual_difficulty,
            "total_reward": round(total_reward, 4),
            "steps_taken": len(history),
            "history": history,
            "success": any(h["grading"].get("total_score", 0) >= 95 for h in history if h.get("grading"))
        }
    
    def _get_action(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        """Query LLM to get action from observation."""
        prompt = self._format_observation(obs)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            return self._parse_action(content)
            
        except Exception as e:
            print(f"⚠️ LLM error: {e}")
            # Return fallback action that won't crash
            return {
                "fixed_sql": "-- LLM Error: " + str(e)[:100],
                "explanation": f"LLM failed: {str(e)}",
                "confidence": 0.0
            }
    
    def _format_observation(self, obs: Dict[str, Any]) -> str:
        """Format observation for LLM prompt"""
        lines = [
            "=== BROKEN MIGRATION ===",
            obs.get("broken_sql", ""),
            "",
            f"Difficulty: {obs.get('difficulty', 'unknown')}",
            f"Step: {obs.get('step_count', 0)}/{obs.get('max_steps', 5)}",
            "",
            "=== DATABASE TYPE ===",
            "SQLite (limited ALTER TABLE support)",
        ]
        
        # Add SQLite guidance for medium/hard
        diff = obs.get("difficulty", "").lower()
        if diff in ["medium", "hard"]:
            lines.extend([
                "",
                "=== SQLITE LIMITATIONS ===",
                "- Cannot add UNIQUE/FOREIGN KEY/CHECK constraints via ALTER TABLE",
                "- Use CREATE UNIQUE INDEX instead of ADD CONSTRAINT UNIQUE",
                "- NOT NULL columns require DEFAULT on existing tables",
                "- Each ALTER TABLE statement must be separate (semicolon required)",
            ])
        
        if obs.get("error_message"):
            lines.extend(["", "=== ERROR MESSAGE ===", obs["error_message"]])
        else:
            lines.extend([
                "",
                "=== STATUS ===",
                "No error message (potential SILENT CORRUPTION - check data carefully!)"
            ])
        
        schema = obs.get("current_schema")
        if schema:
            lines.extend([
                "",
                "=== CURRENT SCHEMA ===",
                f"Table: {schema.get('table_name', 'unknown')}",
                "Columns:"
            ])
            for col in schema.get("columns", []):
                null_str = "NOT NULL" if col.get("notnull") else "NULL"
                default = col.get("dflt_value") or "None"
                lines.append(f"  - {col.get('name', '?')} ({col.get('type', '?')}) {null_str} DEFAULT {default}")
        
        if obs.get("sample_data"):
            lines.extend([
                "",
                "=== SAMPLE DATA (First 5 rows) ===",
                json.dumps(obs["sample_data"], indent=2)
            ])
        
        if obs.get("hint"):
            lines.extend(["", f"=== HINT ===", obs["hint"]])
        
        lines.extend(["", "Provide your fix in the required JSON format."])
        
        return "\n".join(lines)
    
    def _parse_action(self, content: str) -> Dict[str, Any]:
        """Parse LLM response into action dict"""
        try:
            # Handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            
            return {
                "fixed_sql": data.get("fixed_sql", "").strip(),
                "explanation": data.get("explanation", "").strip(),
                "confidence": float(data.get("confidence", 0.5))
            }
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON parse error: {e}")
            return {
                "fixed_sql": content[:500],
                "explanation": "Parse error - raw response used",
                "confidence": 0.3
            }
        except Exception as e:
            print(f"⚠️ Unexpected parse error: {e}")
            return {
                "fixed_sql": "-- Parse error",
                "explanation": str(e),
                "confidence": 0.0
            }


def main():
    """
    Main entry point - runs ALL 3 tasks as required by OpenEnv spec.
    Outputs JSON to stdout (no file writes - HF Spaces is read-only).
    """
    print("=" * 60)
    print("SQL Migration Safety Gym - Baseline Agent")
    print("=" * 60)
    print(f"Model: {MODEL_NAME}")
    print(f"API Base: {API_BASE_URL}")
    print(f"Env URL: {ENV_URL}")
    print("=" * 60)
    
    # Create agent
    agent = SQLMigrationAgent()
    
    # Run all 3 tasks as required by spec
    scores = {}
    
    for task_id in ["easy", "medium", "hard"]:
        print(f"\n{'='*60}")
        print(f"TASK: {task_id.upper()}")
        print(f"{'='*60}")
        
        try:
            result = agent.run_episode(task_id=task_id, verbose=True)
            
            # Extract final score from last step's grading
            final_score = 0.0
            if result.get("history"):
                last_grading = result["history"][-1].get("grading", {})
                final_score = last_grading.get("total_score", 0) / 100.0
            
            scores[task_id] = round(final_score, 4)
            
            print(f"\n📊 Task {task_id} Final Score: {final_score:.4f}")
            
        except Exception as e:
            print(f"❌ Task {task_id} failed: {e}")
            scores[task_id] = 0.0
    
    # Calculate average
    avg_score = sum(scores.values()) / 3 if scores else 0.0
    
    print("\n" + "=" * 60)
    print("BASELINE RESULTS")
    print("=" * 60)
    print(f"  easy   → {scores.get('easy', 0):.4f}")
    print(f"  medium → {scores.get('medium', 0):.4f}")
    print(f"  hard   → {scores.get('hard', 0):.4f}")
    print(f"  AVG    → {avg_score:.4f}")
    print("=" * 60)
    
    # CRITICAL: Output JSON to stdout (no file writes)
    final_results = {
        "model": MODEL_NAME,
        "scores": scores,
        "average": round(avg_score, 4),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    
    print("\n📋 FINAL JSON OUTPUT:")
    print(json.dumps(final_results, indent=2))
    
    # Return for programmatic use
    return final_results


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        sys.exit(1)