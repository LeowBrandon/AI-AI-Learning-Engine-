@echo off
REM ============================================================
REM  Open the frontend in the default browser.
REM
REM  The frontend is pure static HTML/CSS/JS with no build step,
REM  and it works fine over the file:// protocol (the backend
REM  allows cross-origin requests), so no web server is needed.
REM
REM  NOTE: this file is intentionally ASCII-only and does NOT run
REM  "chcp". Changing the console code page inside a .bat makes
REM  cmd.exe mis-seek in the file, which silently breaks the script.
REM ============================================================

setlocal

set "APP=%~dp0frontend\index.html"

if not exist "%APP%" goto missing

echo Opening the app in your default browser ...
start "" "%APP%"

echo.
echo   %APP%
echo.
echo   NOTE: the backend must be running, otherwise the dot at the
echo         top-right of the page stays red. Run start_backend.bat
echo         first if you have not already.
echo.
pause
goto done


:missing
echo.
echo   [ERROR] frontend\index.html not found next to this script.
echo.
echo   Keep start_frontend.bat in the project root folder, together
echo   with the frontend and backend folders.
echo.
pause
exit /b 1


:done
endlocal
