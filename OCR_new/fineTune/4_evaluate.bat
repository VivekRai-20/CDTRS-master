@echo off
rem STEP 4 - compare the handwriting models on your test lines (see README.md)
cd /d "%~dp0.."
call "%~dp0..\..\scripts\find_python.bat" || (pause & exit /b 1)
%PY% fineTune\evaluation\evaluate.py --show 10 --report %*
pause
