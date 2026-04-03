"""
training_demo.py — Generate reward curve for README

Runs 20 episodes against the live HF Space (or local server) using
LLaMA-3.1-8B via Groq, then plots a reward curve PNG.

Usage:
    export GROQ_API_KEY=gsk_your_key_here
    export ENV_URL=https://shyamalancode-sql-migration-env.hf.space   # or http://localhost:7860
    python training_demo.py

Output:
    reward_curve.png  — add this to git, embed in README
"""

import os
import sys
import json
import uuid
import requests

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

# ── CONFIG ──────────────────────────────────────────────────────────────────
ENV_URL   = os.environ.get("ENV_URL", "https://shyamalancode-sql-migration-env.hf.space")
API_KEY   = os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY")
API_BASE  = os.environ.get("API_BASE_URL", "https://api.groq.com/openai/v1")
MODEL     = os.environ.get("MODEL_NAME", "llama-3.1-8b-instant")
EPISODES  = 20

if API_KEY and _OPENAI_AVAILABLE:
    client = OpenAI(base_url=API_BASE, api_key=API_KEY)
    print(f"[OK] LLM client initialized ({MODEL})")
else:
    client = None
    print("[WARN] No GROQ_API_KEY/OPENAI_API_KEY or openai package — using rule-based agent fallback")

# ── PROMPT ───────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a SQL migration expert specializing in SQLite.
Your task: given a broken SQL migration script, write a corrected version.

Rules:
- SQLite supports ALTER TABLE ... ADD COLUMN only (not DROP COLUMN in older versions)
- Each ALTER TABLE statement must be separate (no comma-separated columns)
- NOT NULL columns require a DEFAULT value when added to existing tables
- Use single quotes for string literals, not double quotes
- Wrap multi-step migrations in BEGIN; ... COMMIT; transactions
- For silent corruption: think carefully about execution ORDER

Return ONLY the corrected SQL statement(s). No explanation, no markdown fences."""

# ── RUN EPISODES ─────────────────────────────────────────────────────────────
rewards_per_episode = []
difficulties = ["easy", "medium", "hard"]

print(f"\n{'='*60}")
print(f"  SQL Migration Safety Gym — Reward Curve Demo")
print(f"  Environment: {ENV_URL}")
print(f"  Model: {MODEL}")
print(f"  Episodes: {EPISODES}")
print(f"{'='*60}\n")

for episode in range(EPISODES):
    difficulty = difficulties[episode % 3]
    session_id = str(uuid.uuid4())  # New isolated session per episode
    req_headers = {"Content-Type": "application/json", "X-Session-ID": session_id}

    # Reset
    try:
        reset_resp = requests.post(
            f"{ENV_URL}/reset",
            json={"task_id": difficulty},
            headers=req_headers,
            timeout=30
        )
        reset_resp.raise_for_status()
        obs = reset_resp.json()
    except Exception as e:
        print(f"Episode {episode+1:02d} ({difficulty:6s}): RESET FAILED — {e}")
        rewards_per_episode.append(0.0)
        continue

    # Build prompt
    user_prompt = f"""Fix this broken SQL migration.

SCENARIO: {obs.get('description', 'N/A')}
DIFFICULTY: {obs.get('difficulty', difficulty).upper()}
ERROR: {obs.get('error_message') or '(no error — possible SILENT CORRUPTION)'}
SCHEMA: {json.dumps(obs.get('current_schema'), indent=2) if obs.get('current_schema') else 'N/A'}
SAMPLE DATA: {json.dumps(obs.get('sample_data'), indent=2) if obs.get('sample_data') else 'N/A'}
HINT: {obs.get('hint') or '(no hint — hard mode)'}

BROKEN SQL:
{obs.get('broken_sql', '')}

Return ONLY the corrected SQL."""

    # LLM call (or rule-based fallback)
    if client:
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=512,
            )
            fixed_sql = response.choices[0].message.content.strip()
            # Strip markdown fences if present
            if fixed_sql.startswith("```"):
                fixed_sql = "\n".join(fixed_sql.split("\n")[1:])
            if fixed_sql.endswith("```"):
                fixed_sql = "\n".join(fixed_sql.split("\n")[:-1])
            fixed_sql = fixed_sql.strip()
        except Exception as e:
            print(f"Episode {episode+1:02d} ({difficulty:6s}): LLM FAILED — {e}")
            rewards_per_episode.append(0.0)
            continue
    else:
        # Rule-based fallback: just submit the broken SQL as-is (produces 0 reward baseline)
        fixed_sql = obs.get('broken_sql', 'SELECT 1;')
        if not fixed_sql.strip().endswith(';'):
            fixed_sql += ';'

    # Submit fix
    try:
        step_resp = requests.post(
            f"{ENV_URL}/step",
            json={
                "fixed_sql": fixed_sql,
                "explanation": f"Fix for {obs.get('scenario_id','?')}",
                "confidence": 0.75
            },
            headers=req_headers,
            timeout=30
        )
        step_resp.raise_for_status()
        result = step_resp.json()
        reward = result.get("reward", 0.0)
        score  = result.get("info", {}).get("grading_result", {}).get("total_score", 0.0)
    except Exception as e:
        print(f"Episode {episode+1:02d} ({difficulty:6s}): STEP FAILED — {e}")
        rewards_per_episode.append(0.0)
        continue

    rewards_per_episode.append(reward)
    bar = "#" * int(reward * 30)
    print(f"Episode {episode+1:02d} ({difficulty:6s}): reward={reward:.4f}  score={score:5.1f}/100  [{bar:<30}]")

# ── SUMMARY ──────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
avg = sum(rewards_per_episode) / len(rewards_per_episode) if rewards_per_episode else 0
print(f"  Average reward: {avg:.4f}")
easy_avg   = sum(rewards_per_episode[i] for i in range(0, EPISODES, 3)) / max(1, sum(1 for i in range(0, EPISODES, 3)))
medium_avg = sum(rewards_per_episode[i] for i in range(1, EPISODES, 3)) / max(1, sum(1 for i in range(1, EPISODES, 3)))
hard_avg   = sum(rewards_per_episode[i] for i in range(2, EPISODES, 3)) / max(1, sum(1 for i in range(2, EPISODES, 3)))
print(f"  Easy avg:   {easy_avg:.4f}")
print(f"  Medium avg: {medium_avg:.4f}")
print(f"  Hard avg:   {hard_avg:.4f}")
print(f"{'='*60}\n")

# ── PLOT ─────────────────────────────────────────────────────────────────────
try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor('#0f172a')
    ax.set_facecolor('#0d1929')

    colors = ['#4ade80' if difficulties[i % 3] == 'easy' else
              '#fbbf24' if difficulties[i % 3] == 'medium' else
              '#f87171' for i in range(len(rewards_per_episode))]

    ax.bar(range(1, len(rewards_per_episode) + 1), rewards_per_episode, color=colors, alpha=0.85, width=0.7)
    ax.plot(range(1, len(rewards_per_episode) + 1), rewards_per_episode, 'w-o',
            linewidth=1.5, markersize=5, alpha=0.6)

    ax.axhline(y=avg, color='#6366f1', linestyle='--', linewidth=1.5, label=f'Mean ({avg:.3f})')
    ax.axhline(y=0.5, color='#94a3b8', linestyle=':', linewidth=1, alpha=0.5, label='0.50 baseline')

    # Legend patches
    easy_patch   = mpatches.Patch(color='#4ade80', label=f'Easy (avg {easy_avg:.3f})')
    medium_patch = mpatches.Patch(color='#fbbf24', label=f'Medium (avg {medium_avg:.3f})')
    hard_patch   = mpatches.Patch(color='#f87171', label=f'Hard (avg {hard_avg:.3f})')
    mean_line    = plt.Line2D([0],[0], color='#6366f1', linestyle='--', label=f'Overall mean ({avg:.3f})')

    ax.legend(handles=[easy_patch, medium_patch, hard_patch, mean_line],
              facecolor='#1e293b', edgecolor='#334155', labelcolor='#e2e8f0', fontsize=10)

    ax.set_xlabel('Episode', color='#94a3b8', fontsize=11)
    ax.set_ylabel('Reward (0–1)', color='#94a3b8', fontsize=11)
    ax.set_title(f'LLaMA-3.1-8B Agent — SQL Migration Safety Gym ({EPISODES} Episodes)',
                 color='#e2e8f0', fontsize=13, fontweight='bold', pad=14)
    ax.set_ylim(0, 1.05)
    ax.set_xlim(0.5, len(rewards_per_episode) + 0.5)
    ax.tick_params(colors='#64748b')
    ax.spines['bottom'].set_color('#1e293b')
    ax.spines['left'].set_color('#1e293b')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', color='#1e293b', linewidth=0.8)

    plt.tight_layout()
    plt.savefig('reward_curve.png', dpi=150, bbox_inches='tight', facecolor='#0f172a')
    print("Saved: reward_curve.png")
    print("Add it to git and embed in README with: ![Reward Curve](reward_curve.png)")

except ImportError:
    print("matplotlib not installed — skipping plot.")
    print("Install with: pip install matplotlib")
    print("\nRaw rewards:", rewards_per_episode)
