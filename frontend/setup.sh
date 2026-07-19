#!/usr/bin/env bash
# One-time frontend setup. Safe to re-run.
set -e
cd "$(dirname "$0")"

echo "=== 1/2: Installing dependencies ==="
npm install --legacy-peer-deps

echo
echo "=== 2/2: Preparing .env ==="
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
else
  echo ".env already exists, skipping."
fi

echo
echo "============================================"
echo "Frontend setup complete."
echo "Run ./start.sh to launch the dev server."
echo "(Make sure the backend is already running — see backend/start.sh)"
echo "============================================"
