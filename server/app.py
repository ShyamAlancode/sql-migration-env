"""
Server entry point wrapper for SQL Migration Safety Gym.
Exposes `app` for uvicorn: server.app:app
"""
from app.main import app  # noqa: F401 - re-export for uvicorn

import uvicorn


def main():
    uvicorn.run(app, host="0.0.0.0", port=7860)


if __name__ == "__main__":
    main()