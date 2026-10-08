@echo off
title AccessPPT Launcher
echo ===================================================
echo           Starting AccessPPT Services
echo ===================================================
echo.

cd /d "%~dp0"

echo [1/2] Launching Backend API (FastAPI on http://127.0.0.1:8000)...
start "AccessPPT Backend (FastAPI)" cmd /k "cd /d ""%~dp0backend"" && .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo [2/2] Launching Frontend Web App (Next.js on http://localhost:3000)...
start "AccessPPT Frontend (Next.js)" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"

echo.
echo ===================================================
echo AccessPPT is starting up!
echo   Frontend : http://localhost:3000
echo   API Docs : http://127.0.0.1:8000/api/docs
echo   Demo User: demo@accessppt.com / Password123!
echo ===================================================
echo.
timeout /t 3 >nul
start http://localhost:3000
