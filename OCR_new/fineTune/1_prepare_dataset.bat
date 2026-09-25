@echo off
rem STEP 1 - cut the scans in datasets\raw into line images (see README.md)
cd /d "%~dp0.."
call "%~dp0..\..\scripts\find_python.bat" || (pause & exit /b 1)
%PY% fineTune\prepare_dataset.py %*
pause
