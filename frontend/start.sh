#!/usr/bin/env bash
# Starts the frontend dev server. Leave this running while you use the app.
set -e
cd "$(dirname "$0")"

if [ ! -d node_modules ]; then
  echo "node_modules not found — run ./setup.sh first."
  exit 1
fi
if [ ! -f .env ]; then
  echo ".env not found — run ./setup.sh first."
  exit 1
fi

echo "Starting frontend at http://localhost:5173 ..."
echo "Make sure the backend is already running in another terminal."
echo "Press Ctrl+C to stop."
npm run dev
