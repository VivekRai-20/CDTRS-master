@echo off
title CDTRS
rem Starts the CDTRS desktop application (settings: frontend\.env - CDTRS_API_URL).
cd /d "%~dp0"
call "%~dp0scripts\find_python.bat" || (pause & exit /b 1)
%PY% main.py %*
if errorlevel 1 pause
