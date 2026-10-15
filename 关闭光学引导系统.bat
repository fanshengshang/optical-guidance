@echo off
setlocal
set "ROOT=%~dp0"
set "PY="

if exist "%ROOT%.venv\Scripts\python.exe" set "PY=%ROOT%.venv\Scripts\python.exe"
if defined PY goto run

where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto run

where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto run

echo.
echo [ERROR] Python not found. Please install Python 3.12 (64-bit) and add it to PATH.
echo.
pause
exit /b 1

:run
%PY% "%ROOT%scripts\runtime\launcher.py" stop
echo.
pause
endlocal
