#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "$OPENAI_API_KEY" ]; then
  echo "OPENAI_API_KEY is not set. Continuing with deterministic root-cause briefs."
fi

echo "Starting backend…"
cd "$SCRIPT_DIR/backend"
uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

echo "Installing frontend deps (first run may take a minute)…"
cd "$SCRIPT_DIR/frontend"
npm install --silent

echo "Starting frontend…"
npm start &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
