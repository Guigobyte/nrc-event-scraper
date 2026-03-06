@echo off
cd /d "%~dp0"
python -m streamlit run dashboard/app.py --server.port 8501
pause
