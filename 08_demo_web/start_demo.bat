@echo off
cd /d "%~dp0.."
echo ============================================================
echo   PetroPID-Agent DCS Web Demo starting on http://127.0.0.1:8000
echo ============================================================
start "" http://127.0.0.1:8000
python 08_demo_web\app.py
pause
