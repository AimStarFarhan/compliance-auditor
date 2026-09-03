@echo off
title Quantum Forgers - Compliance Auditor
echo ============================================
echo  Quantum Forgers - Compliance Auditor
echo  Starting backend + frontend...
echo ============================================
echo.

:: kill anything already on our ports
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 .*LISTENING"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173 .*LISTENING"') do taskkill /PID %%a /F >nul 2>&1

:: start backend (cwd is inherited by 'start', so no nested quotes needed)
cd /d "%~dp0backend"
echo [1/2] Starting backend (FastAPI on :8000)...
start "qf-backend" /min cmd /k "python -m uvicorn app.main:app --port 8000"

:: wait without stdin redirection (ping instead of timeout)
ping -n 7 127.0.0.1 >nul

:: start frontend
cd /d "%~dp0frontend"
echo [2/2] Starting frontend (Vite on :5173)...
start "qf-frontend" /min cmd /k "npm run dev"

ping -n 6 127.0.0.1 >nul

echo.
echo Backend  : http://localhost:8000/docs
echo Frontend : http://localhost:5173
echo.
start http://localhost:5173
echo Both running in minimized windows ("qf-backend", "qf-frontend").
echo Close those windows to stop the servers.
