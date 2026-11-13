@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
 echo Installing ForgeApply dependencies in local virtual environment...
 py -3.13 -m venv .venv
 if errorlevel 1 (python -m venv .venv)
 .venv\Scripts\python.exe -m pip install --upgrade pip
 .venv\Scripts\python.exe -m pip install -r requirements.txt
 .venv\Scripts\python.exe -m playwright install chromium
)
start "" "http://127.0.0.1:8765"
.venv\Scripts\python.exe -m forgeapply
pause
