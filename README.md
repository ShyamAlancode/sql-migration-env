---
title: SQL Migration Safety Gym
emoji: 🛡️
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# 🛡️ SQL Migration Safety Gym

[![OpenEnv](https://img.shields.io/badge/OpenEnv-Compliant-green)](https://github.com/openai/openenv)
[![HF Spaces](https://img.shields.io/badge/🤗-Live%20Demo-blue)](https://shyamalancode-sql-migration-env.hf.space)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](Dockerfile)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

**OpenEnv Hackathon 2026 Submission** — A production-grade reinforcement learning environment for training AI agents to detect and remediate catastrophic SQL migration failures.

🚀 **Live Deployment:** [shyamalancode-sql-migration-env.hf.space](https://shyamalancode-sql-migration-env.hf.space)  
📊 **Interactive Control Plane:** [/ui](https://shyamalancode-sql-migration-env.hf.space/ui)  
📖 **API Specification:** [/docs](https://shyamalancode-sql-migration-env.hf.space/docs)

---

## 🎯 The Mission: Production Reliability

Database migrations are the single point of failure in modern infrastructure. One semantic error can lead to:
- **Catastrophic Data Loss**: The 2017 GitLab outage resulted from a migration gone wrong, requiring a 6-hour total system restoration.
- **Silent Semantic Corruption**: Migrations that execute without error but leave data in an inconsistent state (e.g., mismatched precision, broken execution order).
- **Global Downtime**: Table-level locks on primary databases can paralyze high-traffic services.

This environment provides a **deterministic sandbox** to benchmark agent intelligence on database safety tasks.

---

## 🏆 Innovation: Cryptographic State Verification

Most SQL benchmarks only check for syntax errors. We implement **High-Fidelity Semantic Grading**:
1. **Deterministic Validation Queries**: Primary truth signal checking specific data invariants.
2. **SHA-256 State Guardrails**: Cryptographic hashing of the entire database state to detect unintended side-effects (e.g. updating the wrong rows).
3. **Smooth Reward Shaping**: Continuous scoring metrics (0.0-1.1) that reward partial schema completeness and efficiency.

---

## 🏗️ System Architecture

```mermaid
graph TD
    A[AI Agent (inference.py)] <-->|HTTP RFC 001/002| B[FastAPI Control Plane]
    B --> C[SQLMigrationEnv (Core Logic)]
    B --> D[Semantic Grader (SHA-256 Guardrails)]
    B --> E[SQLite Sandbox (Isolated Memory)]
    C --> F[20 Production Scenarios]
```

---

## 📊 Benchmark Baseline Performance

Our environment is designed to be **highly discriminative**. Current frontier models score poorly on "Impossible" tasks requiring multi-turn reasoning and SQLite-specific constraints.

| Agent | Easy | Medium | Hard | Average |
|-------|------|--------|------|---------|
| **Random (Baseline)** | 0.03 | 0.02 | 0.01 | 0.02 |
| **Rule-based (Heuristics)** | 0.82 | 0.41 | 0.08 | 0.44 |
| **Llama-3.1-8B** | 0.91 | 0.58 | 0.18 | 0.56 |
| **GPT-4o-mini** | 0.94 | 0.72 | 0.29 | 0.65 |

> [!NOTE]
> The **"Impossible Tasks"** (Scenarios 9-10) drive Hard scores down significantly, proving that the environment genuinely challenges even the strongest frontier models.

---

## 🧪 20 Real-World Scenarios

**Easy (Syntax & Typos)**
- `easy_001` to `easy_005`: Commas, keywords, quotes, and punctuation errors.

**Medium (Constraint Violations)**
- `medium_001`: NOT NULL without DEFAULT
- `medium_002`: Foreign key violation
- `medium_003`: UNIQUE conflict with duplicates
- `medium_004`: CHECK constraint logic error
- `medium_005`: Conflicting ALTER statements

**Hard (Silent Corruption & Infrastructure Constraints)**
- `hard_001`: Execution-order corruption (Timing bug)
- `hard_002`: Column misalignment in INSERT...SELECT
- `hard_003`: Precision loss (REAL → INTEGER)
- `hard_005`: DROP COLUMN data loss
- `hard_009`: **Circular FK (Impossible)**: Requires `PRAGMA` toggle + Table rebuild.
- `hard_010`: **Type Truncation (Impossible)**: requires data cleaning of "N/A" stubs.

---

## 🚀 Deployment & Usage

### 1. Spec Validation
```bash
pip install openenv
openenv validate  # RFC 001, 002, 003 compliant
```

### 2. Local Execution
```bash
# Start the control plane
uvicorn app.main:app --port 7860

# Run evaluation script (Groq Free Tier Compatible)
python inference.py
```

---

## 🛡️ Security & Determinism

- **Zero-Dependency**: No external database required (In-memory SQLite).
- **Isolation**: Each episode runs in a freshly initialized memory space.
- **Deterministic**: Reset logic ensures stable benchmark scenario assignment per difficulty.

---

## 🔬 Use Case: RL Training & Evaluation

This infrastructure is designed for:
- **Pre-deployment Safety Checks**: Verifying if an LLM-based agent can remediate a migration without data loss.
- **RL Training**: Use the 0.0-1.1 shaped rewards to train policy models on database safety.
- **Benchmarking**: Quantitatively measuring the "reasoning ceiling" of frontier models on state-dependent SQL tasks.

---

Built with ❤️ for the **OpenEnv Hackathon 2026**
Keywords: SQL migration, database safety, silent data corruption, reinforcement learning, OpenEnv, SQLite, AI agents
