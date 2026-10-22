@echo off
title GL.iNet Network Monitor
cd /d "%~dp0"
echo =======================================================
echo          GL.iNet Gateway Network Monitor
echo       Ueberwacht Rechner & aufgerufene Webadressen
echo =======================================================
echo.
python main.py
pause
