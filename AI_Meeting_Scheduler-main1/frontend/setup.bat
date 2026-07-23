@echo off
REM One-time frontend setup. Safe to re-run.
setlocal

cd /d "%~dp0"

echo === 1/2: Installing dependencies ===
call npm install --legacy-peer-deps
if errorlevel 1 (
    echo.
    echo FAILED installing dependencies. See the error above.
    exit /b 1
)

echo.
echo === 2/2: Preparing .env ===
if not exist .env (
    copy .env.example .env >nul
    echo Created .env from .env.example
) else (
    echo .env already exists, skipping.
)

echo.
echo ============================================
echo Frontend setup complete.
echo Run start.bat to launch the dev server.
echo (Make sure the backend is already running - see backend\start.bat)
echo ============================================
