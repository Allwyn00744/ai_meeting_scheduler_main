@echo off
REM Starts the frontend dev server. Leave this window open while you use the app.
setlocal

cd /d "%~dp0"

if not exist node_modules (
    echo node_modules not found - run setup.bat first.
    exit /b 1
)
if not exist .env (
    echo .env not found - run setup.bat first.
    exit /b 1
)

echo Starting frontend at http://localhost:5173 ...
echo Make sure the backend is already running in another window.
echo Press Ctrl+C to stop.
call npm run dev
