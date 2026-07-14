@echo off
cd /d "%~dp0"
echo Starting Skip Loading Interface...
echo.
echo Keep this window open while using the interface.
echo URL: http://127.0.0.1:8000
echo.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
) else (
  py app.py
)
pause
