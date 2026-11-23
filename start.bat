@echo off
setlocal
cd /d "%~dp0"
if not exist backend\.venv call setup.bat || exit /b 1
call backend\.venv\Scripts\activate.bat
cd backend
echo Open http://127.0.0.1:8000/docs  (Ctrl+C to stop)
uvicorn app.main:app --host 127.0.0.1 --port 8000
