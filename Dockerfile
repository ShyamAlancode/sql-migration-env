# SQL Migration Safety Gym - OpenEnv Hackathon 2026
# Professional Deployment Infrastructure

FROM python:3.11-slim

# Build-time configurations
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860 \
    HF_HOME=/tmp/huggingface

WORKDIR /app

# Install system dependencies for build stability
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies using the standardized package layout
COPY pyproject.toml .
COPY requirements.txt .
RUN pip install --no-cache-dir -e .

# Copy application source
COPY . .

# Security hardening: running as non-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 7860

# Production-grade health monitoring
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:7860/health')"

# Entry point using the correct app module
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
