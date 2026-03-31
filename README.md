---
title: SQL Migration Safety Gym
emoji: 🛡️
colorFrom: blue
colorTo: red
sdk: docker
pinned: false
---

# 🛡️ SQL Migration Safety Gym

**OpenEnv Hackathon 2026 Submission**

An OpenEnv environment where AI agents learn to fix dangerous SQL migration scripts before they corrupt production databases.

## 🎯 Mission

Database migrations are high-risk operations. A single bad migration can:
- Delete production data
- Lock tables for hours  
- Corrupt records silently (worst case)

This environment trains AI agents to review, analyze, and fix broken migrations with **deterministic safety guarantees**.

## 🏆 Key Features

- **15 Test Scenarios**: 5 Easy (syntax), 5 Medium (constraints), 5 Hard (silent corruption)
- **Silent Corruption Detection**: Hard mode tests catch UPDATE-without-WHERE and data scrambling bugs that defeat GPT-4o
- **Deterministic Grading**: Pure sqlite3 grading engine (25% of hackathon score)
- **OpenEnv Compliant**: Full `reset()` / `step()` / `state()` API

## 🚀 Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 7860

# Test health
curl http://localhost:7860/health

# Run inference (requires OPENAI_API_KEY)
python inference.py
```

### Docker Deployment

```bash
# Build
docker build -t sql-migration-env .

# Run
docker run -p 7860:7860 -e OPENAI_API_KEY=$OPENAI_API_KEY sql-migration-env
```

## 📡 API Endpoints

| Endpoint     | Method | Description             |
| ------------ | ------ | ----------------------- |
| `/health`    | GET    | Health check            |
| `/reset`     | POST   | Start new episode       |
| `/step`      | POST   | Execute action          |
| `/state`     | GET    | Current observation     |
| `/stats`     | GET    | Episode statistics      |
| `/scenarios` | GET    | List test scenarios     |
| `/spec`      | GET    | OpenEnv compliance info |


## 🔍 Silent Corruption Examples
Hard Mode Scenario: `hard_001_update_no_where`

Broken SQL:
```sql
UPDATE user_settings SET theme = 'auto', notifications = 0;
```
*Missing WHERE clause! Updates ALL users instead of just user_id=1. Agent must detect this and add WHERE user_id = 1 to prevent mass corruption.*

## 📝 Tech Stack
- Python 3.11
- FastAPI + Pydantic v2
- SQLite3 (deterministic grading)
- OpenAI Client (inference.py)
- Docker + HF Spaces

Built with 🛡️ for the OpenEnv Hackathon 2026.

## 🔬 Technical Innovation

### Silent Corruption Detection
Traditional SQL graders check for syntax errors. **We check for semantic correctness**:

1. **Pre-migration hash**: SHA-256 of all table contents
2. **Post-migration validation**: Expected query results vs actual
3. **Corruption flag**: Set when data changes unexpectedly

This catches bugs that pass syntax checks but destroy data:
- `UPDATE table SET col=val` (missing WHERE)
- `INSERT INTO new SELECT * FROM old` (column misalignment)
- `ALTER TABLE DROP COLUMN` (irreversible data loss)

### Deterministic Grading
Using SQLite `:memory:` databases ensures:
- Zero network dependencies
- Identical execution across runs
- 100% reproducible scores

### Curriculum Learning Ready
Environment supports progressive difficulty:
- Easy: Syntax (agents learn SQL grammar)
- Medium: Constraints (agents learn schema design)
- Hard: Corruption (agents learn data integrity)
