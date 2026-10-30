@echo off
TITLE Fish Speech CUDA API Server (RTX 4050 6GB)
COLOR 0A
echo Starting Fish Speech GPU API Server on http://127.0.0.1:8080...
cd /d "D:\doc\Smart Home Startup\fish_speech_repo"
..\.venv\Scripts\python.exe -m tools.api_server --listen 127.0.0.1:8080 --device cuda --half
pause
