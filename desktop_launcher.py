"""
DichAudio Desktop Launcher — Chạy backend + WebUI cùng lúc
"""
import subprocess, sys, os, threading, time, webbrowser, signal

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

processes = []

def start_server():
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", "8002"])
    processes.append(p)
    return p

def start_webui():
    env = os.environ.copy()
    env["STREAMLIT_EMAIL"] = ""
    p = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "server/webui/app.py",
                          "--server.port=8501", "--server.headless=true"], env=env)
    processes.append(p)
    return p

def cleanup(signum=None, frame=None):
    for p in processes:
        try: p.terminate()
        except: pass
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

print("=== DichAudio Desktop ===")
print("Khoi dong backend...")
start_server()
time.sleep(3)

print("Khoi dong WebUI...")
start_webui()
time.sleep(4)

print("Mo trinh duyet...")
webbrowser.open("http://127.0.0.1:8501")
print(f"\nBackend: http://127.0.0.1:8002")
print(f"WebUI:   http://127.0.0.1:8501")
print("Nhan Ctrl+C de tat.\n")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    cleanup()
