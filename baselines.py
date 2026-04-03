"""
baselines.py — Baseline agents for SQL Migration Safety Gym
Implements Random, Heuristic, and LLM-based agents to establish performance floors.
"""
import os
import json
import re
import requests
from typing import Dict, Any, List
from openai import OpenAI

# Configuration
ENV_URL = os.environ.get("ENV_URL", "http://localhost:7860")
API_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("GROQ_API_KEY")
API_BASE = os.environ.get("API_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("MODEL_NAME", "gpt-4o-mini")

class BaseAgent:
    def act(self, obs: Dict[str, Any]) -> str:
        raise NotImplementedError

class RandomAgent(BaseAgent):
    """Returns a simple constant query"""
    def act(self, obs: Dict[str, Any]) -> str:
        return "SELECT 1;"

class HeuristicAgent(BaseAgent):
    """Uses simple regex rules to fix common easy/medium errors"""
    def act(self, obs: Dict[str, Any]) -> str:
        broken_sql = obs.get("broken_sql", "")
        error = obs.get("error_message", "")
        
        # Rule 1: Missing comma between ADD COLUMN
        if "ADD COLUMN" in broken_sql and "near \"ADD\":" in error:
            return broken_sql.replace("ADD COLUMN", ", ADD COLUMN").replace("ALTER TABLE users ,", "ALTER TABLE users")
        
        # Rule 2: NOT NULL without DEFAULT
        if "NOT NULL" in broken_sql and "DEFAULT" not in broken_sql:
            return broken_sql.replace("NOT NULL", "NOT NULL DEFAULT ''")
            
        return broken_sql

class LLMAgent(BaseAgent):
    """Uses a frontier LLM to reason about the migration"""
    def __init__(self):
        self.client = OpenAI(api_key=API_KEY, base_url=API_BASE)
        
    def act(self, obs: Dict[str, Any]) -> str:
        prompt = f"Fix this broken SQL migration:\n\nScenario: {obs['description']}\nBroken SQL: {obs['broken_sql']}\nError: {obs.get('error_message') or 'None'}\n\nReturn ONLY the fixed SQL."
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response.choices[0].message.content.strip().replace("```sql", "").replace("```", "")

def run_benchmark():
    agents = {
        "Random": RandomAgent(),
        "Heuristic": HeuristicAgent(),
        "LLM": LLMAgent() if API_KEY else None
    }
    
    difficulties = ["easy", "medium", "hard"]
    results = {}

    for name, agent in agents.items():
        if not agent: continue
        results[name] = {}
        for diff in difficulties:
            r = requests.post(f"{ENV_URL}/reset", json={"task_id": diff})
            obs = r.json()["observation"]
            fixed_sql = agent.act(obs)
            step_r = requests.post(f"{ENV_URL}/step", json={"fixed_sql": fixed_sql})
            results[name][diff] = step_r.json()["reward"]

    # Print Markdown Table
    print("| Agent | Easy | Medium | Hard | Avg |")
    print("|-------|:---:|:---:|:---:|:---:|")
    for name, scores in results.items():
        avg = sum(scores.values()) / len(scores)
        print(f"| {name} | {scores['easy']:.2f} | {scores['medium']:.2f} | {scores['hard']:.2f} | {avg:.2f} |")

if __name__ == "__main__":
    run_benchmark()
