@echo off
cd /d "%~dp0"
echo Starting Skip Loading Interface for LAN access...
echo.
echo Keep this window open while colleagues use the interface.
echo Ask IT for this computer's IP address, then open:
echo http://YOUR-COMPUTER-IP:8000
echo.
set HOST=0.0.0.0
set PORT=8000
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py
) else (
  py app.py
)
pause
