@echo off
cd /d "%~dp0"
echo Creating Python virtual environment...
py -m venv .venv
if errorlevel 1 goto error
echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
echo.
echo Setup completed.
echo Run run_server.cmd for local access.
echo Run run_lan_server.cmd for colleagues on the same network.
pause
exit /b 0

:error
echo.
echo Setup failed. Please make sure Python 3 is installed and available as "py".
pause
exit /b 1
