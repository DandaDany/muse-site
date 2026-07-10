@echo off
setlocal

cd /d "%~dp0"

set "GIT_EXE=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
if not exist "%GIT_EXE%" set "GIT_EXE=git"

rem 先從後台匯出追蹤電影 -> 電影清單.txt，再爬蟲、匯出 GeoJSON（git 交給下方處理）
py -3 scripts\daily_update.py --no-git
if errorlevel 1 (
  echo.
  echo [ERROR] Update failed.
  pause
  exit /b 1
)

echo.
"%GIT_EXE%" add .
if errorlevel 1 (
  echo.
  echo [ERROR] git add failed.
  pause
  exit /b 1
)

"%GIT_EXE%" diff --cached --quiet
if not errorlevel 1 (
  echo [DONE] Map updated, but there are no Git changes to publish.
  echo.
  pause
  exit /b 0
)

"%GIT_EXE%" commit -m "Update map data"
if errorlevel 1 (
  echo.
  echo [ERROR] git commit failed.
  pause
  exit /b 1
)

"%GIT_EXE%" push
if errorlevel 1 (
  echo.
  echo [ERROR] git push failed.
  pause
  exit /b 1
)

echo.
echo [DONE] Map data updated and pushed to GitHub.
echo GitHub Pages will deploy automatically.
echo.
pause
