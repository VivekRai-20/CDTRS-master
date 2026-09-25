@echo off
rem STEP 2 - type the correct text of each line image (see README.md)
cd /d "%~dp0.."
call "%~dp0..\..\scripts\find_python.bat" || (pause & exit /b 1)
%PY% fineTune\label_tool.py %*
if errorlevel 1 pause
