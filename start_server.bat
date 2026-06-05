@echo off
cd /d D:\DIchAudio
title DichAudio Server
echo ============================================
echo  DichAudio Server - Backend API
echo ============================================
echo.
python -m uvicorn server.main:app --host 127.0.0.1 --port 8002 --reload
pause
