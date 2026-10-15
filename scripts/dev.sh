#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:$PATH"

if [[ ! -x "$ROOT/backend/.venv/bin/uvicorn" ]]; then
  echo "Backend is not installed. Run scripts/setup.sh first."
  exit 1
fi

cd "$ROOT/backend"
./.venv/bin/uvicorn app.main:app --reload --port 8000 &
BACK_PID=$!

cd "$ROOT/frontend"
npm run dev -- --port 3000 &
FRONT_PID=$!

trap 'kill $BACK_PID $FRONT_PID 2>/dev/null || true' INT TERM EXIT
wait
