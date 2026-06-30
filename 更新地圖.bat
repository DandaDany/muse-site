@echo off
setlocal

cd /d "%~dp0"

py -3 scripts\update_map.py
if errorlevel 1 (
  echo.
  echo [ERROR] Update failed.
  pause
  exit /b 1
)
echo.
pause
