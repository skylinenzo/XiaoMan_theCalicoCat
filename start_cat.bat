@echo off
setlocal
cd /d "%~dp0"
if exist proxy.local.bat call proxy.local.bat
if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv
    if errorlevel 1 goto error
)
.venv\Scripts\python.exe -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 goto error
)
.venv\Scripts\python.exe desktop_cat.py
if errorlevel 1 goto error
exit /b 0
:error
echo Please install Python 3.10+ for Windows, then try again.
pause
