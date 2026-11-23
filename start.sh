#!/usr/bin/env bash
# Sets up on first run, then starts the server at http://127.0.0.1:8000/docs
cd "$(dirname "$0")"
[ -d backend/.venv ] || ./setup.sh || exit 1
cd backend && . .venv/bin/activate && exec uvicorn app.main:app --host 127.0.0.1 --port 8000
