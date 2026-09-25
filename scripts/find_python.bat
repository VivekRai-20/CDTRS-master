@echo off
rem ---------------------------------------------------------------------------
rem Sets PY to the Python 3.12 that has the CDTRS packages (see imp.txt).
rem Used by the other .bat files:   call "%~dp0find_python.bat" || exit /b 1
rem To use a different Python, set CDTRS_PYTHON to its python.exe first.
rem ---------------------------------------------------------------------------
set "PY="
if defined CDTRS_PYTHON set PY="%CDTRS_PYTHON%"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%ProgramFiles%\Python312\python.exe" set PY="%ProgramFiles%\Python312\python.exe"
if not defined PY (
    where py >nul 2>nul && py -3.12 -c "import sys" >nul 2>nul && set "PY=py -3.12"
)
if not defined PY (
    echo Python 3.12 was not found. Install it, or set CDTRS_PYTHON to the full path of python.exe.
    exit /b 1
)
exit /b 0
