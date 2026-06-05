@echo off
cd /d D:\DIchAudio
title DichAudio Celery Worker
echo ============================================
echo  DichAudio Celery Worker
echo ============================================
echo.
echo Yeu cau: Redis dang chay tren localhost:6379
echo.
python -m celery -A server.celery_app worker --loglevel=info --pool=threads --concurrency=2
pause
