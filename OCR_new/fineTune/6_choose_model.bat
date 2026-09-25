@echo off
rem List handwriting models / choose the active one:  6_choose_model.bat v2
cd /d "%~dp0.."
call "%~dp0..\..\scripts\find_python.bat" || (pause & exit /b 1)
%PY% fineTune\set_active_model.py %*
pause
