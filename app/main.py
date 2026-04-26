"""
app/main.py — stub that redirects to backend entrypoint.

This file exists because the repo has a root-level `app/` package.
The real application lives in backend/app/main.py.

If you are seeing import errors, run the server from the project root:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""
import sys, os
_backend = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
if os.path.abspath(_backend) not in [os.path.abspath(p) for p in sys.path]:
    sys.path.insert(0, os.path.abspath(_backend))

# Now the real backend/app/main.py will be importable as app.main
# Import is done by the caller (root main.py) — nothing to do here.
