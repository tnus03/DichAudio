@echo off
cd /d D:\DIchAudio
set STREAMLIT_EMAIL=
python -m streamlit run server/webui/app.py --server.port=8501 --server.headless=true --browser.gatherUsageStats=false
pause
