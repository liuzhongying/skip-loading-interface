@echo off
cd /d "%~dp0"

rem Change these two paths to your team's shared folder before running.
set SKIP_LOADING_DB_PATH=\\SERVER\SharedFolder\skip-loading-interface\data\skip_loading.db
set SKIP_LOADING_EXPORT_DIR=\\SERVER\SharedFolder\skip-loading-interface\exports

set HOST=127.0.0.1
set PORT=8000

echo Starting Skip Loading Interface with shared database...
echo DB: %SKIP_LOADING_DB_PATH%
echo Exports: %SKIP_LOADING_EXPORT_DIR%
echo URL: http://127.0.0.1:8000
echo.
echo Keep this window open while using the interface.
echo.

"%~dp0skip-loading-interface.exe"
pause
