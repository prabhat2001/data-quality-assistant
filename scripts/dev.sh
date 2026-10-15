#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:$PATH"

if [[ ! -x "$ROOT/backend/.venv/bin/python" ]]; then
  echo "Backend is not installed. Run scripts/setup.sh first."
  exit 1
fi

cd "$ROOT/backend"
./.venv/bin/python manage.py runserver 127.0.0.1:8000 &
BACK_PID=$!

cd "$ROOT/frontend"
npm run dev -- --port 3000 &
FRONT_PID=$!

trap 'kill $BACK_PID $FRONT_PID 2>/dev/null || true' INT TERM EXIT
wait
