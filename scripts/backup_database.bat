@echo off
rem Backs up the CDTRS database and uploaded documents into the "backups" folder.
rem Options:  backup_database.bat --dest D:\cdtrs_backups --keep 30
cd /d "%~dp0..\backend"
call "%~dp0find_python.bat" || (pause & exit /b 1)
%PY% backup_database.py %*
if errorlevel 1 pause
