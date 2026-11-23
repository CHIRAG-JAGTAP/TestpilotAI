@echo off
setlocal
cd /d "%~dp0"
call backend\.venv\Scripts\activate.bat
cd backend
python -m app.database.cli backup
