---
title: SQL Migration Safety Gym
emoji: 🛡️
colorFrom: blue
colorTo: red
sdk: docker
pinned: false
---

# SQL Migration Safety Gym
**OpenEnv Hackathon 2026 Submission**

The SQL Migration Safety Gym is a deterministic reinforcement learning environment designed to evaluate and train AI agents in the detection and remediation of high-risk database migrations. It provides 15 structured scenarios ranging from syntax errors to silent data corruption, ensuring that agents can maintain data integrity in production-critical workflows.

## Mission Overview
Database migrations are high-stakes operations where failure can lead to catastrophic data loss or prolonged system downtime. This environment provides a standardized "Gym" where agents must analyze broken SQL migrations and propose verified fixes that preserve schema integrity and row-level data.

## Key Technical Features
- **15 Scenarios**: Categorized into Easy (Syntax), Medium (Constraints), and Hard (Semantic/Silent Corruption).
- **Silent Corruption Detection**: Advanced validation logic that identifies semantic errors—such as missing WHERE clauses—that pass standard SQL syntax checks but destroy data.
- **Deterministic Evaluation Engine**: Utilizes an isolated SQLite3 memory-based grader to ensure 100% reproducible scoring without external dependencies.
- **OpenEnv Specification Compliance**: Implements the standard `reset()`, `step()`, and `state()` API interfaces.

## Quick Start Technical Guide

### Local Development and Testing
1. **Dependency Installation**:
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

2. **Server Execution**:
   ```bash
   uvicorn server.app:app --host 0.0.0.0 --port 7860
   ```

3. **Performance Audit**:
   ```bash
   python test_submission.py
   ```

### Docker Deployment
The environment is containerized for seamless deployment to Hugging Face Spaces or private infrastructure.

```bash
docker build -t sql-migration-gym .
docker run -p 7860:7860 -e OPENAI_API_KEY=$OPENAI_API_KEY sql-migration-gym
```

## API Specification

| Endpoint | Method | Functional Description |
| :--- | :--- | :--- |
| `/health` | GET | Operational health status monitoring. |
| `/reset` | POST | Initialization of a new task or episode. |
| `/step` | POST | Execution of an agent-provided SQL action. |
| `/state` | GET | Telemetry regarding the current environment state. |
| `/scenarios`| GET | Inventory of available test cases and metadata. |
| `/spec` | GET | OpenEnv v1 compliance identification. |

## Scientific Innovation: Semantic Validation
Traditional SQL graders typically verify syntax or final schema state. This environment introduces **Semantic Row Hashing**:
1. **Pre-Snapshot**: The environment captures a SHA-256 hash of all table content before the migration.
2. **Execution**: The agent's proposed fix is applied to a sandbox clone.
3. **Integrity Audit**: The grader compares the post-fix results against expected outcomes.
4. **Corruption Flag**: If the agent's SQL affects rows that should have remained untouched (e.g., global updates), the `is_silent_corruption` flag is triggered, resulting in a significant penalty.

## Technical Requirements
- Python 3.11+
- FastAPI / Pydantic v2
- SQLite3
- Docker (for deployment)

Developed for the OpenEnv Hackathon 2026.
