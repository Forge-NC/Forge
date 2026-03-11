@echo off
REM Forge Adaptive Nightly Tests — Windows Task Scheduler wrapper
REM
REM Task Scheduler setup:
REM   Program: C:\Users\theup\Desktop\Forge\scripts\nightly.bat
REM   Start in: C:\Users\theup\Desktop\Forge
REM   Trigger: Daily at 3:00 AM
REM   Conditions: Start only if computer is on AC power (optional)

cd /d "%~dp0\.."
set PYTHON=.venv\Scripts\python.exe
%PYTHON% scripts/nightly_smart.py --non-interactive %*
exit /b %ERRORLEVEL%
