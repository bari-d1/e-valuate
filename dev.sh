#!/usr/bin/env bash
# Start backend (FastAPI :8000) and frontend (Vite :5173) together. Ctrl+C stops both.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/cw_board_evaluation"
FRONTEND="$ROOT/cw-board-ui"
VENV="$BACKEND/.venv-mac"

# First-run setup
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating Python environment..."
  python3.14 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$BACKEND/requirements.txt"
fi
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd "$FRONTEND" && npm ci)
fi

if ! pg_isready -q -h localhost -p 5432; then
  echo "Postgres isn't running. Start it with: brew services start postgresql@18" >&2
  exit 1
fi

# Apply any new migrations
(cd "$BACKEND" && "$VENV/bin/alembic" upgrade head >/dev/null 2>&1)

trap 'kill 0' EXIT

(cd "$BACKEND" && "$VENV/bin/python" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 2>&1 | sed -l 's/^/[api] /') &
(cd "$FRONTEND" && npm run dev -- --host 127.0.0.1 --port 5173 2>&1 | sed -l 's/^/[web] /') &

echo "App: http://127.0.0.1:5173/consultant  (Ctrl+C to stop)"
wait
