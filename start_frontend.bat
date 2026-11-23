@echo off
cd /d "%~dp0frontend"
if not exist node_modules call npm install || exit /b 1
echo Open http://localhost:5173  (backend must be running: start.bat)
call npm run dev
