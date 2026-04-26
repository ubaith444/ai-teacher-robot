#!/usr/bin/env bash
# run.sh – Start the AI Teacher Robot Backend (Zoro)
# ─────────────────────────────────────────────────────────────────────────────
# Usage:
#   chmod +x run.sh
#   ./run.sh            # production mode
#   ./run.sh --dev      # development mode (auto-reload, debug logging)
#   ./run.sh --migrate  # run DB migrations only, then exit
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[ZORO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERR]${NC}  $*"; }

# ── Always run from project root ──────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
info "Working directory: $SCRIPT_DIR"

# ── Load .env ─────────────────────────────────────────────────────────────────
if [[ -f ".env" ]]; then
    set -o allexport; source .env; set +o allexport
    info "Loaded .env"
else
    warn "No .env found. Copy .env.example to .env and fill in your values."
fi

# ── Python check ──────────────────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    error "Python not found. Install Python 3.10+."; exit 1
fi

PYVER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python version: $PYVER"

# ── Virtualenv ────────────────────────────────────────────────────────────────
for VENV_DIR in venv .venv backend/venv; do
    if [[ -d "$VENV_DIR" ]]; then
        if [[ -f "$VENV_DIR/bin/activate" ]]; then
            source "$VENV_DIR/bin/activate"
        elif [[ -f "$VENV_DIR/Scripts/activate" ]]; then
            source "$VENV_DIR/Scripts/activate"
        fi
        info "Activated virtualenv: $VENV_DIR"; break
    fi
done

# ── Install dependencies ──────────────────────────────────────────────────────
if ! python -c "import fastapi" 2>/dev/null; then
    warn "FastAPI not found. Installing requirements..."
    pip install -r requirements.txt --quiet
fi

# ── Migrations (alembic.ini is at project root, always run from here) ─────────
run_migrations() {
    info "Running database migrations..."
    # PYTHONPATH must include backend/ so alembic env.py can import app.models
    PYTHONPATH="${SCRIPT_DIR}/backend:${PYTHONPATH:-}" alembic upgrade head \
        || { error "Migrations failed. Check DATABASE_URL in your .env"; exit 1; }
    ok "Migrations complete."
}

if [[ "${1:-}" == "--migrate" ]]; then
    run_migrations; exit 0
fi

run_migrations

# ── Server config ─────────────────────────────────────────────────────────────
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

cleanup() { warn "Shutdown signal — bye."; }
trap cleanup SIGINT SIGTERM EXIT

# ── Start (always from project root, PYTHONPATH includes backend/) ────────────
export PYTHONPATH="${SCRIPT_DIR}/backend:${PYTHONPATH:-}"

if [[ "${1:-}" == "--dev" ]]; then
    info "Starting DEVELOPMENT mode on http://${HOST}:${PORT} ..."
    exec uvicorn main:app \
        --host "$HOST" --port "$PORT" \
        --reload --reload-dir backend \
        --log-level debug
else
    info "Starting PRODUCTION mode on http://${HOST}:${PORT} ..."
    exec uvicorn main:app \
        --host "$HOST" --port "$PORT" \
        --workers 1 \
        --log-level info \
        --access-log
fi
