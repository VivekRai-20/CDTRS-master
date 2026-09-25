@echo off
title CDTRS backend
rem Starts the CDTRS backend (settings: backend\.env - HOST, PORT, DATABASE_URL, ...).
rem Keep this window open while CDTRS is in use; close it to stop the server.
cd /d "%~dp0backend"
call "%~dp0scripts\find_python.bat" || (pause & exit /b 1)
if not exist .env (
    echo backend\.env is missing. Copy backend\.env.example to backend\.env and set DATABASE_URL.
    pause
    exit /b 1
)
%PY% run_server.py %*
echo.
echo The backend has stopped.
pause
