@echo off
REM Forge Nightly Stress Tests — Windows Task Scheduler wrapper
REM
REM Task Scheduler setup:
REM   Program: C:\Users\theup\Desktop\Forge\scripts\nightly.bat
REM   Start in: C:\Users\theup\Desktop\Forge
REM   Trigger: Daily at 3:00 AM
REM   Conditions: Start only if computer is on AC power (optional)

cd /d "%~dp0\.."

set PYTHON=.venv\Scripts\python.exe
set TIMESTAMP=%date:~-4%%date:~4,2%%date:~7,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%
set LOG_DIR=%USERPROFILE%\.forge\nightly_logs

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ============================================
echo   Forge Nightly Stress Test
echo ============================================

echo.
echo [1/2] Running --live --full (1 iteration)...
%PYTHON% scripts/run_live_stress.py --live --full -n 1 > "%LOG_DIR%\nightly_full_%TIMESTAMP%.log" 2>&1
set FULL_EXIT=%ERRORLEVEL%

echo.
echo [2/2] Running --live --soak (1 iteration)...
%PYTHON% scripts/run_live_stress.py --live --soak -n 1 > "%LOG_DIR%\nightly_soak_%TIMESTAMP%.log" 2>&1
set SOAK_EXIT=%ERRORLEVEL%

echo.
echo ============================================
if %FULL_EXIT%==0 (echo   Full: PASS) else (echo   Full: FAIL)
if %SOAK_EXIT%==0 (echo   Soak: PASS) else (echo   Soak: FAIL)
echo   Logs: %LOG_DIR%
echo ============================================

REM Regenerate dashboard
%PYTHON% scripts/view_stress_results.py --no-open 2>nul

exit /b %FULL_EXIT%
