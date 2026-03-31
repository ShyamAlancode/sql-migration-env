"""
Inference script for SQL Migration Safety Gym
REQUIRED FILE - OpenEnv Hackathon 2026

This script implements an AI agent that interacts with the sql-migration-env
environment using the OpenAI client interface.
"""

import os
import json
import time
import requests
from typing import Optional, Dict, Any
from openai import OpenAI
from pydantic import BaseModel
from app.models import Action, Observation


class SQLMigrationAgent:
    """
    AI Agent for fixing SQL migration scripts.
    
    Usage:
        agent = SQLMigrationAgent(model="gpt-4o")
        results = agent.run_episode(difficulty="hard")
    """
    
    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        env_url: str = "http://localhost:7860"
    ):
        """
        Initialize agent.
        
        Args:
            model: Model identifier (gpt-4o, gpt-3.5-turbo, etc.)
            api_key: OpenAI API key (or compatible)
            base_url: Base URL for API (None for OpenAI, or local LLM URL)
            env_url: URL of the sql-migration-env server
        """
        self.model = model
        self.env_url = env_url
        
        # Initialize OpenAI client
        self.client = OpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY", "dummy"),
            base_url=base_url
        )
        
        self.system_prompt = """You are an expert Database Migration Engineer.
Your task is to review broken SQL migration scripts and fix them before they corrupt production databases.

CRITICAL RULES:
1. Preserve ALL existing data - never lose rows
2. Respect constraints - handle NOT NULL with DEFAULT values
3. Watch for SILENT CORRUPTION (HARD mode):
   - UPDATE without WHERE updates ALL rows (disaster!)
   - Column misalignment in INSERT...SELECT scrambles data
   - Wrong defaults overwrite historical data
   - Type coercion loses precision

RESPONSE FORMAT:
You must respond with valid JSON:
{
    "fixed_sql": "The corrected SQL migration script",
    "explanation": "Brief explanation of what was wrong and how you fixed it",
    "confidence": 0.95
}

SCORING CRITERIA:
- Syntax correct (20%)
- Data integrity preserved (40%)
- Schema achieved (30%)
- Efficiency (10%)

Be careful. Be precise. Check your work."""
        
    def run_episode(
        self,
        scenario_id: Optional[str] = None,
        difficulty: Optional[str] = None,
        max_steps: int = 5,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Run one full episode.
        
        Returns:
            Dict with episode stats, history, and final score
        """
        if verbose:
            print(f"Starting episode with model: {self.model}")
            if scenario_id:
                print(f"   Scenario: {scenario_id}")
            if difficulty:
                print(f"   Difficulty: {difficulty}")
        
        # Reset environment
        reset_payload = {}
        if scenario_id:
            reset_payload["scenario_id"] = scenario_id
        if difficulty:
            reset_payload["difficulty"] = difficulty
            
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
                print(f"Action: {action.explanation[:100]}...")
                print(f"SQL: {action.fixed_sql[:80]}...")
            
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
                print(f"Reward: {reward:.3f} | Done: {done}")
                if info.get("grading_result"):
                    gr = info["grading_result"]
                    print(f"   Score: {gr['total_score']:.1f}/100")
                    if gr.get("silent_corruption_detected"):
                        print(f"   Silent corruption detected!")
            
            if done:
                if verbose:
                    print(f"\nEpisode complete!")
                break
        
        # Get final stats
        stats_response = requests.get(f"{self.env_url}/stats")
        stats = stats_response.json() if stats_response.status_code == 200 else {}
        
        return {
            "model": self.model,
            "scenario_id": obs.scenario_id,
            "difficulty": obs.difficulty,
            "total_reward": total_reward,
            "steps_taken": len(history),
            "history": history,
            "final_stats": stats,
            "success": any(h["grading"]["total_score"] >= 95 for h in history)
        }
    
    def _get_action(self, obs: Observation) -> Action:
        """
        Query LLM to get action from observation.
        """
        # If dummy api key is used, do not call OpenAI to avoid auth errors in testing.
        if self.client.api_key == "dummy":
            return Action(
                fixed_sql="-- DUMMY ACTION",
                explanation="Dummy run since no API key provided.",
                confidence=0.5
            )

        prompt = self._format_observation(obs)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,  # Low temp for precision
                max_tokens=1000,
                response_format={"type": "json_object"}  # For GPT-4o JSON mode
            )
            
            content = response.choices[0].message.content
            return self._parse_action(content)
            
        except Exception as e:
            print(f"LLM error: {e}")
            # Fallback: return empty action
            return Action(
                fixed_sql="-- ERROR: Failed to generate fix",
                explanation=f"Error calling LLM: {str(e)}",
                confidence=0.0
            )
    
    def _format_observation(self, obs: Observation) -> str:
        """Format observation for LLM prompt"""
        lines = [
            "=== BROKEN MIGRATION ===",
            obs.broken_sql,
            "",
            f"Difficulty: {obs.difficulty}",
            f"Step: {obs.step_count}/{obs.max_steps}",
        ]
        
        if obs.error_message:
            lines.extend([
                "",
                "=== ERROR MESSAGE ===",
                obs.error_message
            ])
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
            lines.extend([
                "",
                f"=== HINT ===",
                obs.hint
            ])
        
        lines.extend([
            "",
            "Provide your fix in the required JSON format."
        ])
        
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
            print(f"JSON parse error: {e}")
            # Try to extract SQL from raw text
            return Action(
                fixed_sql=content[:500],  # Truncate
                explanation="Parse error - raw response used",
                confidence=0.3
            )
        except Exception as e:
            print(f"Unexpected parse error: {e}")
            return Action(
                fixed_sql="-- Parse error",
                explanation=str(e),
                confidence=0.0
            )


def main():
    """
    Main entry point for running inference.
    Configurable via environment variables.
    """
    # Configuration
    model = os.getenv("AGENT_MODEL", "gpt-4o")
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")  # For local LLMs
    env_url = os.getenv("ENV_URL", "http://localhost:7860")
    difficulty = os.getenv("DIFFICULTY", "easy")
    scenario_id = os.getenv("SCENARIO_ID")  # Optional specific scenario
    
    if not api_key:
        print("WARNING: OPENAI_API_KEY not set. Using dummy mode.")
    
    # Create agent
    agent = SQLMigrationAgent(
        model=model,
        api_key=api_key,
        base_url=base_url,
        env_url=env_url
    )
    
    # Run episode
    print("=" * 50)
    print("SQL Migration Safety Gym - Agent Inference")
    print("=" * 50)
    
    results = agent.run_episode(
        scenario_id=scenario_id,
        difficulty=difficulty,
        verbose=True
    )
    
    # Print summary
    print("\n" + "=" * 50)
    print("EPISODE SUMMARY")
    print("=" * 50)
    print(f"Scenario: {results['scenario_id']}")
    print(f"Difficulty: {results['difficulty']}")
    print(f"Total Reward: {results['total_reward']:.3f}")
    print(f"Steps: {results['steps_taken']}")
    print(f"Success: {'YES' if results['success'] else 'NO'}")
    
    # Save results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"results_{results['scenario_id']}_{timestamp}.json"
    with open(filename, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {filename}")


if __name__ == "__main__":
    main()
