@echo off
rem STEP 3 - fine-tune the handwriting model on your labelled lines (see README.md)
rem This can take hours.  Keep the window open; the log is also saved in
rem fineTune\checkpoints\train_handwriting.log
cd /d "%~dp0.."
call "%~dp0..\..\scripts\find_python.bat" || (pause & exit /b 1)
if not exist fineTune\checkpoints mkdir fineTune\checkpoints
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
%PY% fineTune\training\train.py --task handwriting %* 2>&1 | %PY% fineTune\tee.py fineTune\checkpoints\train_handwriting.log
pause
