# OpenEnv Hackathon 2026: Submission Protocol
**SQL Migration Safety Gym**

This document provides definitive instructions for final deployment and validation of the SQL Migration Safety Gym as a Round 1 submission.

## 1. Pre-Submission Checklist
Ensure every component listed here is verified before proceeding to the final submission.

- **Source Integrity**: All 15 scenarios must be implemented in `app/scenarios.py`.
- **OpenEnv Specification**:
    - [x] `/reset` accepts `task_id` for difficulty or scenario ID.
    - [x] `/step` returns `Observation`, `reward`, `done`, and `info`.
    - [x] `/spec` identifies as `openenv-v1`.
- **Infrastructure**:
    - [x] `Dockerfile` uses standard `uvicorn server.app:app`.
    - [x] `pyproject.toml` contains valid professional metadata.
- **Documentation**:
    - [x] `README.md` includes required Hugging Face frontmatter.
    - [x] `inference.py` is included in the base repository.

## 2. Deployment to Hugging Face Spaces
The following steps ensure a successful build on the Hugging Face platform.

### Environment Setup
1. **Repository Link**: Pushing `sql-migration-env` to your Hugging Face Space.
2. **Space Configuration**:
    - **SDK**: Docker
    - **Port**: 7860 (standard)
3. **Secrets Management**:
    - Define `OPENAI_API_KEY` in the **Settings > Secrets** section of your Space to enable `inference.py` verification.

### Log Monitoring
After deployment, monitor the container logs for the message:
`Uvicorn running on http://0.0.0.0:7860 (Press CTRL+C to quit)`

## 3. Post-Deployment API Verification
Verify accessibility of the production endpoints using the following commands:

```bash
# Verify Health Status
curl https://huggingface.co/spaces/ShyamAlancode/sql-migration-env/api/health

# Verify OpenEnv Specification
curl https://huggingface.co/spaces/ShyamAlancode/sql-migration-env/api/spec
```

## 4. Evaluation of Competitive Metrics
The submission targets the following performance benchmarks for judging:

- **Real-world Utility (30%)**: The focus on database migration hazards—a common production issue—provides high business utility.
- **Task/Grader Quality (25%)**: The inclusion of silent corruption detection via SHA-256 state hashing ensures high-fidelity grading.
- **Environment Design (20%)**: Unified Pydantic models (v2) and isolated SQLite sandboxing provide extreme stability.
- **Spec Compliance (15%)**: Full alignment with the OpenEnv v1 standard.
- **Innovation (10%)**: The semantic corruption flag for non-syntactic SQL logical errors.

## 5. Contact Information
For technical inquiries regarding this environment, please refer to the documentation in the repository or consult the OpenEnv technical guidelines.
