@echo off
setlocal
cd /d "%~dp0"
echo === TestPilot setup (Phase 1: database foundation) ===
python --version || (echo Python 3.11+ is required: https://www.python.org/downloads/ & exit /b 1)
if not exist backend\.venv python -m venv backend\.venv
call backend\.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt || exit /b 1
cd backend
python -m app.database.cli init || exit /b 1
python -m app.database.cli health
echo.
echo Setup complete. Run run_tests.bat to verify.
