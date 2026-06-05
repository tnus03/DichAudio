# DichAudio Desktop Build Script
# Chay file nay de build thanh .exe
# Yeu cau: pip install pyinstaller

import os, sys, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

# Cai dat pyinstaller neu chua co
try:
    import PyInstaller
except ImportError:
    os.system(f"{sys.executable} -m pip install pyinstaller")

# Build
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--name", "DichAudio",
    "--windowed",
    "--add-data", f"server{os.pathsep}server",
    "--add-data", f"resource{os.pathsep}resource",
    "--hidden-import", "uvicorn",
    "--hidden-import", "streamlit",
    "--hidden-import", "gtts",
    "--hidden-import", "edge_tts",
    "--hidden-import", "sqlalchemy",
    "--hidden-import", "aiosqlite",
    "--hidden-import", "cloudinary",
    "--collect-all", "streamlit",
    "desktop_launcher.py"
]

print("Building DichAudio Desktop...")
subprocess = __import__("subprocess")
r = subprocess.run(cmd, capture_output=False)
if r.returncode == 0:
    print(f"\nThanh cong! File exe o: dist/DichAudio/DichAudio.exe")
else:
    print(f"\nBuild that bai.")
