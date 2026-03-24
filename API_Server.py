"""API Server 실행 스크립트."""

import os
import subprocess
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.join(ROOT_DIR, "API_Server")


def main():
    # .env 로드
    env = os.environ.copy()
    dotenv_path = os.path.join(ROOT_DIR, ".env")
    if os.path.exists(dotenv_path):
        with open(dotenv_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()

    subprocess.run(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--reload", "--host", "0.0.0.0", "--port", "8000"],
        cwd=SERVER_DIR,
        env=env,
    )


if __name__ == "__main__":
    main()