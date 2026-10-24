@echo off
REM ============================================================
REM  Start the backend (Flask API) on http://127.0.0.1:8765
REM
REM  NOTE: this file is intentionally ASCII-only and does NOT run
REM  "chcp". Changing the console code page inside a .bat makes
REM  cmd.exe mis-seek in the file, which silently breaks the script.
REM ============================================================

setlocal
cd /d "%~dp0backend"

set "VENV_PY=.venv\Scripts\python.exe"

REM ---------- 1. virtual environment ----------
if exist "%VENV_PY%" (
  echo [1/3] Virtual environment found: backend\.venv
  goto install
)

echo [1/3] Creating virtual environment backend\.venv ...
set "PY="

where python >nul 2>&1
if not errorlevel 1 set "PY=python"

if not defined PY (
  where py >nul 2>&1
  if not errorlevel 1 set "PY=py"
)

REM fall back to the usual per-user install locations
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"

if not defined PY goto no_python

REM quoted so that a path containing spaces still works
"%PY%" -m venv .venv
if errorlevel 1 goto failed

:install
REM ---------- 2. dependencies ----------
echo [2/3] Installing dependencies (first run takes a minute) ...
"%VENV_PY%" -m pip install --upgrade pip -q
"%VENV_PY%" -m pip install -r requirements.txt -q
if errorlevel 1 goto failed

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo.
  echo   [NOTE] backend\.env was just created from the template.
  echo          Fill in LLM_API_KEY, otherwise chat / quiz / report
  echo          will fail. Everything else works without it.
  echo.
)

REM ---------- 3. run ----------
echo [3/3] Starting backend on http://127.0.0.1:8765
echo       Press Ctrl+C to stop.
echo.

REM open the app first; the dot at its top-right turns green once
REM the server is up (the page re-checks every 8 seconds)
if exist "%~dp0frontend\index.html" start "" "%~dp0frontend\index.html"

"%VENV_PY%" app.py
if errorlevel 1 goto failed

goto done


:no_python
echo.
echo   [ERROR] Python not found.
echo.
echo   Install Python 3.10 or newer and tick "Add Python to PATH".
echo   Download: https://www.python.org/downloads/
echo.
pause
exit /b 1


:failed
echo.
echo   [ERROR] Something went wrong. See the messages above.
echo.
echo   Common causes:
echo     - Port 8765 is already in use (close the other window,
echo       or change PORT in backend\.env)
echo     - No internet while installing dependencies
echo.
pause
exit /b 1


:done
endlocal
