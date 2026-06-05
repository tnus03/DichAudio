"""Debug script — chạy client từng bước, ghi log ra file."""
import sys, traceback
from pathlib import Path

LOG = Path.home() / ".dichaudio" / "debug.log"
LOG.parent.mkdir(parents=True, exist_ok=True)

def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{msg}\n")
    print(msg)

try:
    sys.path.insert(0, "D:/DIchAudio")

    log("1. Importing modules...")
    from client.main import api_call, HAVE_PYQT, get_hwid, Dashboard
    log(f"   HAVE_PYQT={HAVE_PYQT}")

    log("2. Testing API...")
    h = api_call("GET", "/health")
    log(f"   Health: {h}")

    log("3. Testing HWID...")
    hwid = get_hwid()
    log(f"   HWID: {hwid[:30]}...")

    log("4. Creating QApplication...")
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtGui import QFont
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    log("5. Creating Dashboard...")
    d = Dashboard()
    log("6. Showing Dashboard...")
    d.show()

    log("7. Starting event loop. Window should be visible.")
    sys.exit(app.exec())

except SystemExit:
    log("8. App exited normally.")
    raise
except Exception:
    with open(LOG, "a", encoding="utf-8") as f:
        traceback.print_exc(file=f)
    traceback.print_exc()
    input("CRASH — see debug.log. Press Enter...")
    raise
