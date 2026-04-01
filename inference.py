"""
Inference script for SQL Migration Safety Gym
OpenEnv Hackathon 2026 - COMPLIANT VERSION
"""

import os
import json
import time
import requests
from typing import Optional, Dict, Any
from openai import OpenAI
from app.models import Action, Observation, DifficultyLevel


# REQUIRED ENVIRONMENT VARIABLES (exact names per spec)
API_BASE_URL = os.environ.get("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4o-mini")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", HF_TOKEN)  # Fallback to HF_TOKEN
ENV_URL = os.environ.get("ENV_URL", "http://localhost:7860")


class SQLMigrationAgent:
    """
    AI Agent for fixing SQL migration scripts.
    COMPLIANT with OpenEnv Hackathon spec.
    """
    
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        env_url: Optional[str] = None
    ):
        # Use env vars as defaults, allow override
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
   - Clean data first, OR use CREATE UNIQUE INDEX (SQLite allows this even with duplicates if you handle it)

CRITICAL RULES:
1. Preserve ALL existing data - never lose rows
2. Watch for SILENT CORRUPTION (HARD mode):
   - UPDATE without WHERE updates ALL rows
   - Column misalignment in INSERT...SELECT scrambles data

RESPOND WITH JSON:
{
    "fixed_sql": "The corrected SQLite migration script",
    "explanation": "Brief explanation of what was wrong and how you fixed it",
    "confidence": 0.95
}"""
        
    def run_episode(
        self,
        task_id: Optional[str] = None,  # Accept task_id per spec
        difficulty: Optional[str] = None,
        max_steps: int = 5,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Run one full episode.
        
        Args:
            task_id: Task identifier (easy/medium/hard or specific scenario)
            difficulty: Difficulty level (fallback if task_id not provided)
        """
        # Map task_id to difficulty if provided
        effective_difficulty = task_id or difficulty or "easy"
        
        if verbose:
            print(f"🚀 Starting episode with model: {self.model}")
            print(f"   Task/Difficulty: {effective_difficulty}")
        
        # Reset environment - use task_id field per spec
        reset_payload = {}
        if task_id:
            reset_payload["task_id"] = task_id  # PRIMARY: spec-compliant
        if difficulty:
            reset_payload["difficulty"] = difficulty  # Fallback
            
        response = requests.post(f"{self.env_url}/reset", json=reset_payload)
        response.raise_for_status()
        obs = Observation(**response.json())
        
        if verbose:
            print(f"   Loaded scenario: {obs.scenario_id} ({obs.difficulty})")
        
        history = []
        total_reward = 0.0
        
        for step in range(max_steps):
            if verbose:
                print(f"\n--- Step {step + 1}/{max_steps} ---")
            
            # Get action from LLM
            action = self._get_action(obs)
            
            if verbose:
                print(f"📝 Action: {action.explanation[:100]}...")
                print(f"🔧 SQL: {action.fixed_sql[:80]}...")
            
            # Execute step
            step_response = requests.post(
                f"{self.env_url}/step",
                json={
                    "fixed_sql": action.fixed_sql,
                    "explanation": action.explanation,
                    "confidence": action.confidence
                }
            )
            step_response.raise_for_status()
            result = step_response.json()
            
            obs = Observation(**result["observation"])
            reward = result["reward"]
            done = result["done"]
            info = result["info"]
            
            total_reward += reward
            
            history.append({
                "step": step + 1,
                "action": action.model_dump(),
                "reward": reward,
                "grading": info.get("grading_result", {}),
                "done": done
            })
            
            if verbose:
                print(f"⭐ Reward: {reward:.3f} | Done: {done}")
                if info.get("grading_result"):
                    gr = info["grading_result"]
                    print(f"   Score: {gr['total_score']:.1f}/100")
            
            if done:
                if verbose:
                    print(f"\n✅ Episode complete!")
                break
        
        return {
            "model": self.model,
            "scenario_id": obs.scenario_id,
            "difficulty": obs.difficulty,
            "total_reward": total_reward,
            "steps_taken": len(history),
            "history": history,
            "success": any(h["grading"]["total_score"] >= 95 for h in history)
        }
    
    def _get_action(self, obs: Observation) -> Action:
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
            error_msg = f"Error calling LLM: {str(e)}"
            # Truncate to avoid Pydantic >1000 char validation error
            if len(error_msg) > 950:
                error_msg = error_msg[:950] + "... (truncated)"
                
            return Action(
                fixed_sql="-- ERROR: Failed to generate fix",
                explanation=error_msg,
                confidence=0.0
            )
    
    def _format_observation(self, obs: Observation) -> str:
        """Format observation for LLM prompt with SQLite hints"""
        lines = [
            "=== BROKEN MIGRATION ===",
            obs.broken_sql,
            "",
            f"Difficulty: {obs.difficulty}",
            f"Step: {obs.step_count}/{obs.max_steps}",
            "",
            "=== DATABASE TYPE ===",
            "SQLite (limited ALTER TABLE support)",
        ]
        
        # Add SQLite-specific guidance for medium/hard
        if obs.difficulty in [DifficultyLevel.MEDIUM, DifficultyLevel.HARD]:
            lines.extend([
                "",
                "=== SQLITE LIMITATIONS ===",
                "- Cannot add UNIQUE/FOREIGN KEY/CHECK constraints via ALTER TABLE",
                "- Use CREATE UNIQUE INDEX instead of ADD CONSTRAINT UNIQUE",
                "- NOT NULL columns require DEFAULT on existing tables",
                "- Each ALTER TABLE statement must be separate (semicolon required)",
            ])
        
        if obs.error_message:
            lines.extend(["", "=== ERROR MESSAGE ===", obs.error_message])
        else:
            lines.extend([
                "",
                "=== STATUS ===",
                "No error message (potential SILENT CORRUPTION - check data carefully!)"
            ])
        
        if obs.current_schema:
            lines.extend([
                "",
                "=== CURRENT SCHEMA ===",
                f"Table: {obs.current_schema.table_name}",
                "Columns:"
            ])
            for col in obs.current_schema.columns:
                null_str = "NOT NULL" if col.get("notnull") else "NULL"
                default = col.get("dflt_value") or "None"
                lines.append(f"  - {col['name']} ({col['type']}) {null_str} DEFAULT {default}")
        
        if obs.sample_data:
            lines.extend([
                "",
                "=== SAMPLE DATA (First 5 rows) ===",
                json.dumps(obs.sample_data, indent=2)
            ])
        
        if obs.hint:
            lines.extend(["", f"=== HINT ===", obs.hint])
        
        lines.extend(["", "Provide your fix in the required JSON format."])
        
        return "\n".join(lines)
    
    def _parse_action(self, content: str) -> Action:
        """Parse LLM response into Action"""
        try:
            # Handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            
            return Action(
                fixed_sql=data.get("fixed_sql", "").strip(),
                explanation=data.get("explanation", "").strip(),
                confidence=float(data.get("confidence", 0.5))
            )
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON parse error: {e}")
            return Action(
                fixed_sql=content[:500],
                explanation="Parse error - raw response used",
                confidence=0.3
            )
        except Exception as e:
            print(f"⚠️ Unexpected parse error: {e}")
            error_msg = str(e)
            if len(error_msg) > 950:
                error_msg = error_msg[:950] + "... (truncated)"
            return Action(
                fixed_sql="-- Parse error",
                explanation=error_msg,
                confidence=0.0
            )


def main():
    """
    Main entry point - runs ALL 3 tasks as required by spec.
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
    
    # Run exactly the 3 benchmark scenarios to eliminate reproducibility issues
    BENCHMARK_TASKS = {
        "easy":   "easy_001_missing_comma",
        "medium": "medium_005_multiple_alter_conflicts",
        "hard":   "hard_001_update_no_where"
    }
    
    scores = {}
    
    for diff, scenario_id in BENCHMARK_TASKS.items():
        print(f"\n{'='*60}")
        print(f"TASK: {diff.upper()} ({scenario_id})")
        print(f"{'='*60}")
        
        result = agent.run_episode(task_id=scenario_id, verbose=True)
        
        # Extract final score from last step's grading
        final_score = 0.0
        if result["history"]:
            final_score = result["history"][-1]["grading"]["total_score"] / 100.0
        
        scores[diff] = final_score
        
        print(f"\n📊 Task {diff} Final Score: {final_score:.4f}")
    
    # Calculate average
    avg_score = sum(scores.values()) / 3
    
    print("\n" + "=" * 60)
    print("BASELINE RESULTS")
    print("=" * 60)
    print(f"  easy   → {scores['easy']:.4f}")
    print(f"  medium → {scores['medium']:.4f}")
    print(f"  hard   → {scores['hard']:.4f}")
    print(f"  AVG    → {avg_score:.4f}")
    print("=" * 60)
    
    # Return results as JSON to stdout (no file write - HF Spaces is read-only)
    final_results = {
        "model": MODEL_NAME,
        "scores": scores,
        "average": avg_score,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    print("\n📋 FINAL JSON OUTPUT:")
    print(json.dumps(final_results, indent=2))
    
    return final_results


if __name__ == "__main__":
    main()