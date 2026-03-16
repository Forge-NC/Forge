@echo off
title Forge - Local AI Coding Assistant
color 0A

echo.
echo  =============================================
echo   FORGE - Local AI Coding Assistant
echo   No tokens. No compaction. No bullshit.
echo  =============================================
echo.

:: Use embedded venv Python
set "FORGE_DIR=%~dp0"
set "VENV_PYTHON=%FORGE_DIR%.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo  [ERROR] Venv not found. Run install.py first:
    echo    python install.py
    echo.
    pause
    exit /b 1
)

:: Show Python version
for /f "tokens=2 delims= " %%v in ('"%VENV_PYTHON%" --version 2^>^&1') do set PYVER=%%v
echo  [OK] Python %PYVER% (embedded venv)

:: Enable KV cache quantization and flash attention for Ollama
set OLLAMA_FLASH_ATTENTION=1
set OLLAMA_KV_CACHE_TYPE=q8_0
set OLLAMA_MAX_LOADED_MODELS=2

:: Check if Ollama is already running
curl -s http://localhost:11434/api/tags >nul 2>nul
if %errorlevel% equ 0 (
    echo  [OK] Ollama running
    goto :ollama_ready
)

:: Ollama not running — start it with our env vars active
echo  [..] Starting Ollama with KV cache quantization (Q8)...
start "" "ollama" serve

:: Wait loop
set TRIES=0
:wait_ollama
timeout /t 1 /nobreak >nul
curl -s http://localhost:11434/api/tags >nul 2>nul
if %errorlevel% equ 0 (
    echo  [OK] Ollama started (flash_attention=ON, kv_cache=Q8)
    goto :ollama_ready
)
set /a TRIES+=1
if %TRIES% lss 15 goto :wait_ollama

echo  [ERROR] Ollama failed to start after 15 seconds.
echo  Install Ollama from https://ollama.com
echo.
pause
exit /b 1

:ollama_ready
echo.
echo  Starting Forge...
echo  =============================================
echo.

:: Run Forge from the project directory using venv Python
set "FORGE_KEEP_OPEN=1"
pushd "%FORGE_DIR%"
"%VENV_PYTHON%" -m forge --fnc %*
popd

:: Keep window open after exit
echo.
echo  Forge exited. Press any key to close.
pause >nul
