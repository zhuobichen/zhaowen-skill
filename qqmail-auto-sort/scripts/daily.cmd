@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM Daily archive at 00:00, then build the HTML report (resident timer, no admin needed)
node "%~dp0daily.mjs" --at=00:00 --limit=400 >> "%~dp0daily.out" 2>&1
