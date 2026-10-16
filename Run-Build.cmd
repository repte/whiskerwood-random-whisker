@echo off
cd /d "%~dp0"
echo STARTED %DATE% %TIME% > build-console.log
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Automation\RandomWhisker\Build-Mod.ps1" >> build-console.log 2>&1
echo EXIT=%ERRORLEVEL% >> build-console.log
