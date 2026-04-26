"""
main.py — Project root entrypoint for Zoro AI Teacher Robot.

Run from the project root:
    uvicorn main:app --host 0.0.0.0 --port 8000

Or directly:
    python main.py
"""
import sys
import os

# Put backend/ on the path FIRST so `from app.xxx` resolves to backend/app/xxx
# NOT to the root-level app/ stub package.
backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.main import app  # noqa: E402 — must be after sys.path fix

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=1)
