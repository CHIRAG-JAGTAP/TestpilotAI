#!/usr/bin/env bash
# One-command setup for macOS/Linux: venv + dependencies + database.
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3.11+ is required: https://www.python.org/downloads/"; exit 1; }
[ -d backend/.venv ] || python3 -m venv backend/.venv
. backend/.venv/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q -r backend/requirements.txt
cd backend
python -m app.database.cli init
python -m app.database.cli health
echo; echo "Setup complete. Run ./start.sh to launch, ./run_tests.sh to verify."
