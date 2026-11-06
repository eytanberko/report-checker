@echo off
rem Report Checker demo: double-click to start the app on http://localhost:8501 and open it with the public site.
rem The API key is asked for here if it is not already set; it lives only in this window, never in a file.
title Report Checker demo
cd /d "%~dp0"

if not defined DEMO_PORT set "DEMO_PORT=8501"
set "APP_URL=http://localhost:%DEMO_PORT%"
set "SITE_URL=https://eytanberko.github.io/report-checker/"
rem 127.0.0.1, not localhost: on Windows localhost tries IPv6 first and the check can take over 2 s
set "HEALTH=http://127.0.0.1:%DEMO_PORT%/_stcore/health"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.12+ and run: pip install -r requirements.txt
    pause
    exit /b 1
)

rem Already running (e.g. double-clicked twice): just open the pages.
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%HEALTH%' | Out-Null; exit 0 } catch { exit 1 }"
if not errorlevel 1 (
    echo The app is already running.
    if not defined DEMO_NO_BROWSER start "" "%APP_URL%"
    if not defined DEMO_NO_BROWSER start "" "%SITE_URL%"
    timeout /t 3 >nul
    exit /b 0
)

if not defined GEMINI_API_KEY (
    echo GEMINI_API_KEY is not set. Live checks need it; without it the app shows saved runs only.
    set /p "GEMINI_API_KEY=Paste your Gemini API key and press Enter (or just Enter to skip): "
)
if defined GEMINI_API_KEY (echo API key: set for this window.) else (echo API key: none, live checks hidden.)

rem Open both pages once the app answers (up to 60 s), while Streamlit starts in this window.
if not defined DEMO_NO_BROWSER start "" /b powershell -NoProfile -WindowStyle Hidden -Command ^
    "for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%HEALTH%' | Out-Null; break } catch { Start-Sleep 1 } }; Start-Process '%APP_URL%'; Start-Process '%SITE_URL%'"

echo Starting the app on %APP_URL% ... (close this window to stop it)
python -m streamlit run app.py --server.port %DEMO_PORT% --server.headless true --browser.gatherUsageStats false
echo.
echo The app stopped.
pause
