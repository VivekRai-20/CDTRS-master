@echo off
rem Train the printed / handwritten detector on your labelled lines (see README.md)
cd /d "%~dp0.."
call "%~dp0..\..\scripts\find_python.bat" || (pause & exit /b 1)
%PY% fineTune\training\train.py --task text_type %*
%PY% fineTune\evaluation\evaluate.py --task text_type
pause
