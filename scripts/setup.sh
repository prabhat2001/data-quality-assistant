#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PYTHON="${PYTHON:-python3.12}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3.12 is required. Install it, or set PYTHON to another 3.10–3.13 interpreter."
  exit 1
fi

"$PYTHON" -m venv "$ROOT/backend/.venv"
"$ROOT/backend/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"

if [[ ! -f "$ROOT/backend/.env" ]]; then
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
  echo "Created backend/.env from the example. Set DATABASE_URL and, if you have one, GEMINI_API_KEY."
fi

cd "$ROOT/frontend"
npm install
echo "Setup complete."
