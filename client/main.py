# -*- coding: utf-8 -*-
"""
DichAudio Desktop Client — PyQt6
HWID tự động, license key nhập 1 lần, dashboard dịch video.
"""
import hashlib, json, platform, re, subprocess, sys, uuid, time
from pathlib import Path
import requests
import webbrowser

API_BASE = "http://127.0.0.1:8002/api/v1"
CONFIG_FILE = Path.home() / ".dichaudio" / "config.json"

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QDialog, QFrame, QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QBrush
HAVE_PYQT = True


STATUS_ICON = {
    "PENDING": "⏳", "DOWNLOADING": "⬇️", "EXTRACTING_AUDIO": "🎵",
    "TRANSCRIBING": "📝", "TRANSLATING": "🌐", "GENERATING_VOICE": "🗣️",
    "EDITING_AND_MERGING": "🎬", "UPLOADING": "☁️",
    "COMPLETED": "✅", "FAILED": "❌",
}
STATUS_VN = {
    "PENDING": "Chờ xử lý", "DOWNLOADING": "Đang tải video",
    "EXTRACTING_AUDIO": "Tách âm thanh", "TRANSCRIBING": "Nhận diện giọng nói",
    "TRANSLATING": "Đang dịch thuật", "GENERATING_VOICE": "Tạo giọng đọc",
    "EDITING_AND_MERGING": "Ghép video", "UPLOADING": "Đang tải lên",
    "COMPLETED": "Hoàn thành", "FAILED": "Thất bại",
}


def get_hwid() -> str:
    components = []
    try:
        if platform.system() == "Windows":
            for cmd, idx in [
                ("wmic cpu get processorid", 1),
                ("wmic baseboard get serialnumber", 1),
                ("wmic diskdrive get serialnumber", 1),
            ]:
                r = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=5)
                if r.returncode == 0:
                    lines = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
                    if len(lines) > idx: components.append(lines[idx])
            mac_r = subprocess.run("wmic nic where 'NetEnabled=True' get MACAddress",
                                   capture_output=True, text=True, shell=True, timeout=5)
            if mac_r.returncode == 0:
                for line in mac_r.stdout.strip().split("\n"):
                    m = line.strip()
                    if m and re.match(r"^([0-9A-Fa-f]{2}[:-]){5}", m):
                        components.append(m); break
    except Exception: pass
    if not components: components.append(str(uuid.uuid1().node))
    return hashlib.sha256("|".join(components).encode()).hexdigest()


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try: return json.loads(CONFIG_FILE.read_text("utf-8"))
        except Exception: pass
    return {}

def save_config(cfg: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")

def api_call(method: str, path: str, data = None) -> dict:
    url = f"{API_BASE}{path}"
    try:
        if method == "GET": r = requests.get(url, timeout=10)
        else: r = requests.post(url, json=data, timeout=10)
        if r.status_code >= 400:
            return {"error": r.json().get("detail", f"HTTP {r.status_code}")}
        return r.json()
    except requests.ConnectionError:
        return {"error": "Không thể kết nối server"}
    except Exception as e:
        return {"error": str(e)}


STYLE = """
QMainWindow, QDialog { background: #0f172a; color: #e2e8f0; }
QLabel { color: #cbd5e1; font-size: 13px; }
QLineEdit {
    background: #1e293b; border: 1px solid #334155; border-radius: 8px;
    padding: 10px 14px; color: #e2e8f0; font-size: 13px;
}
QLineEdit:focus { border-color: #3b82f6; }
QPushButton { border: none; border-radius: 8px; padding: 10px 24px; font-size: 13px; font-weight: 600; color: white; }
QComboBox {
    background: #1e293b; border: 1px solid #334155; border-radius: 8px;
    padding: 10px 14px; color: #e2e8f0; font-size: 13px;
}
QCheckBox { color: #cbd5e1; font-size: 13px; spacing: 8px; }
QTableWidget {
    background: #1e293b; border: 1px solid #334155; border-radius: 8px;
    color: #e2e8f0; font-size: 12px; gridline-color: #1e293b;
}
QTableWidget::item { padding: 8px; }
QTableWidget::item:selected { background: #1e3a5f; }
QHeaderView::section {
    background: #0f172a; color: #64748b; font-size: 11px; font-weight: 600;
    padding: 10px 8px; border: none; border-bottom: 1px solid #334155;
}
QTextEdit {
    background: #0f172a; border: 1px solid #334155; border-radius: 6px;
    color: #94a3b8; font-size: 12px; font-family: Consolas, monospace;
    padding: 8px;
}
QListWidget {
    background: #0f172a; border: 1px solid #334155; border-radius: 6px;
    color: #94a3b8; font-size: 12px; padding: 4px;
}
QListWidget::item { padding: 4px 8px; border-bottom: 1px solid #1e293b; }
"""


# ===== LICENSE DIALOG =====

class LicenseDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.device_id = get_hwid()
        self.result_data = None
        self.setWindowTitle("Kích hoạt DichAudio")
        self.setFixedSize(460, 300)
        self.setStyleSheet(STYLE)
        self._ui()

    def _ui(self):
        l = QVBoxLayout(self); l.setSpacing(14); l.setContentsMargins(32, 24, 32, 24)
        ti = QLabel("🔑 Kích hoạt DichAudio")
        ti.setStyleSheet("font-size: 20px; font-weight: bold; color: #f1f5f9;")
        ti.setAlignment(Qt.AlignmentFlag.AlignCenter); l.addWidget(ti)
        sb = QLabel("Nhập License Key từ Telegram Bot")
        sb.setStyleSheet("font-size: 12px; color: #64748b;")
        sb.setAlignment(Qt.AlignmentFlag.AlignCenter); l.addWidget(sb); l.addSpacing(8)
        l.addWidget(QLabel("License Key"))
        self.k = QLineEdit()
        self.k.setPlaceholderText("XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"); l.addWidget(self.k)
        dl = QLabel(f"📌 Thiết bị: {self.device_id[:16]}...")
        dl.setStyleSheet("color: #64748b; font-size: 11px;"); l.addWidget(dl); l.addSpacing(4)
        self.btn = QPushButton("Kích hoạt ngay")
        self.btn.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3b82f6,stop:1 #6366f1); padding: 12px;")
        self.btn.clicked.connect(self._activate); l.addWidget(self.btn)
        self.st = QLabel(""); self.st.setAlignment(Qt.AlignmentFlag.AlignCenter); l.addWidget(self.st); l.addStretch()

    def _activate(self):
        key = self.k.text().strip()
        if not key: self.st.setText("❌ Nhập License Key"); return
        self.btn.setEnabled(False); self.btn.setText("Đang kích hoạt...")
        res = api_call("POST", "/license/activate", {"license_key": key, "device_id": self.device_id})
        self.btn.setEnabled(True); self.btn.setText("Kích hoạt ngay")
        if "error" in res: self.st.setText(f"❌ {res['error']}")
        elif res.get("success"):
            self.st.setText(f"✅ Còn {res['remaining_days']} ngày")
            cfg = load_config()
            cfg.update(license_key=key, device_id=self.device_id, expired_at=res.get("expired_at"), remaining_days=res["remaining_days"])
            save_config(cfg); self.result_data = cfg
            QTimer.singleShot(600, self.accept)


# ===== DASHBOARD =====

class Dashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.setWindowTitle("DichAudio - Video Translator")
        self.resize(1020, 720)
        self.setStyleSheet(STYLE)
        self._log_entries = []
        self._ui()
        self._log("🚀 DichAudio khởi động")
        QTimer.singleShot(200, self._check_license)
        self.tmr = QTimer()
        self.tmr.timeout.connect(self._refresh)
        self.tmr.start(3000)

    def _ui(self):
        cw = QWidget(); self.setCentralWidget(cw)
        ml = QVBoxLayout(cw); ml.setSpacing(12); ml.setContentsMargins(20, 12, 20, 12)

        # === HEADER ===
        hd = QWidget(); hl = QHBoxLayout(hd); hl.setContentsMargins(0,0,0,0)
        t = QLabel("DichAudio")
        t.setStyleSheet("font-size: 22px; font-weight: bold; color: #f1f5f9;"); hl.addWidget(t); hl.addStretch()
        self.sdot = QLabel("●")
        self.sdot.setStyleSheet("color: #22c55e; font-size: 16px;"); hl.addWidget(self.sdot)
        self.sin = QLabel("Đang kiểm tra...")
        self.sin.setStyleSheet("color: #94a3b8; font-size: 12px;"); hl.addWidget(self.sin)
        self.btn_rn = QPushButton("Gia hạn")
        self.btn_rn.setStyleSheet("background: #22c55e; color: #052e16; padding: 6px 16px; border-radius: 6px; font-size: 12px;")
        self.btn_rn.setVisible(False); self.btn_rn.clicked.connect(self._license_dlg); hl.addWidget(self.btn_rn)
        ml.addWidget(hd)

        # === BODY: Top row (input + table) ===
        top = QHBoxLayout(); top.setSpacing(16)

        # Left input panel
        lf = QFrame()
        lf.setStyleSheet("QFrame { background: #1e293b; border: 1px solid #334155; border-radius: 12px; }")
        lf.setMaximumWidth(380)
        ll = QVBoxLayout(lf); ll.setContentsMargins(16,16,16,16); ll.setSpacing(10)
        ll.addWidget(self._lb("Dịch video mới", "font-size: 15px; font-weight: 600; color: #f1f5f9;"))
        ll.addWidget(QLabel("URL Video (TikTok, YouTube Shorts)"))
        self.iu = QLineEdit(); self.iu.setPlaceholderText("https://www.tiktok.com/@..."); ll.addWidget(self.iu)
        ll.addWidget(QLabel("Tốc độ"))
        self.cb = QComboBox()
        self.cb.addItems(["1.0x", "1.05x", "1.1x"]); self.cb.setCurrentText("1.05x"); ll.addWidget(self.cb)
        self.cm = QCheckBox("Lật hình (Mirror)")
        self.cb2 = QCheckBox("Blur padding"); self.cw2 = QCheckBox("Watermark")
        ll.addWidget(self.cm); ll.addWidget(self.cb2); ll.addWidget(self.cw2); ll.addSpacing(4)
        self.bt = QPushButton("Dịch ngay")
        self.bt.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #3b82f6,stop:1 #6366f1); padding: 12px; font-size: 14px; font-weight: 600;")
        self.bt.setMinimumHeight(44); self.bt.clicked.connect(self._task); ll.addWidget(self.bt)
        ll.addStretch(); top.addWidget(lf)

        # Right table
        rf = QFrame()
        rf.setStyleSheet("QFrame { background: #1e293b; border: 1px solid #334155; border-radius: 12px; }")
        rl = QVBoxLayout(rf); rl.setContentsMargins(16,16,16,16); rl.setSpacing(8)
        h2 = QHBoxLayout()
        h2.addWidget(self._lb("Lịch sử dịch", "font-size: 15px; font-weight: 600; color: #f1f5f9;"))
        h2.addStretch()
        self.tc = QLabel("0 task"); self.tc.setStyleSheet("color: #64748b; font-size: 12px;"); h2.addWidget(self.tc)
        rl.addLayout(h2)

        self.tb = QTableWidget(0, 5)
        self.tb.setHorizontalHeaderLabels(["#", "Trạng thái", "Task", "Kết quả", "Video"])
        hh = self.tb.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed); self.tb.setColumnWidth(0, 50)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed); self.tb.setColumnWidth(1, 200)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed); self.tb.setColumnWidth(3, 80)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed); self.tb.setColumnWidth(4, 80)
        self.tb.verticalHeader().setVisible(False)
        self.tb.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tb.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # Click vào cột Video để mở
        self.tb.cellClicked.connect(self._on_cell_clicked)
        rl.addWidget(self.tb); top.addWidget(rf)
        ml.addLayout(top)

        # === BOTTOM: Activity log ===
        log_frame = QFrame()
        log_frame.setStyleSheet("QFrame { background: #1e293b; border: 1px solid #334155; border-radius: 12px; }")
        log_layout = QVBoxLayout(log_frame); log_layout.setContentsMargins(16,12,16,12); log_layout.setSpacing(6)
        log_header = QHBoxLayout()
        log_header.addWidget(self._lb("Hoạt động gần đây", "font-size: 13px; font-weight: 600; color: #94a3b8;"))
        log_header.addStretch()
        btn_clear_log = QPushButton("Xóa")
        btn_clear_log.setStyleSheet("background: #334155; color: #94a3b8; padding: 4px 12px; font-size: 11px; border-radius: 4px;")
        btn_clear_log.clicked.connect(lambda: self.log_list.clear())
        log_header.addWidget(btn_clear_log)
        log_layout.addLayout(log_header)
        self.log_list = QListWidget()
        self.log_list.setMaximumHeight(160)
        self.log_list.setStyleSheet("QListWidget { background: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #94a3b8; font-size: 12px; } QListWidget::item { padding: 3px 8px; border-bottom: 1px solid #1e293b; }")
        log_layout.addWidget(self.log_list)
        ml.addWidget(log_frame)

    def _lb(self, t, s): l = QLabel(t); l.setStyleSheet(s); return l

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        item = QListWidgetItem(f"[{ts}] {msg}")
        self.log_list.insertItem(0, item)
        self._log_entries.append(msg)
        # Giữ tối đa 100 dòng
        while self.log_list.count() > 100:
            self.log_list.takeItem(self.log_list.count() - 1)

    # ----- License -----
    def _check_license(self):
        if not self.cfg.get("license_key") or not self.cfg.get("device_id"):
            self._log("🔑 Chưa có license, mở dialog kích hoạt..."); self._license_dlg(); return
        res = api_call("POST", "/license/check", {"license_key": self.cfg["license_key"], "device_id": self.cfg["device_id"]})
        if "error" in res:
            self.sin.setText(f"⚠️ {res['error']}"); self.sdot.setStyleSheet("color: #f59e0b; font-size: 16px;"); self.btn_rn.setVisible(True)
            self._log(f"⚠️ License check: {res['error']}")
        elif res.get("valid"):
            self.sin.setText(f"Còn {res['remaining_days']} ngày"); self.sdot.setStyleSheet("color: #22c55e; font-size: 16px;")
            self.cfg["remaining_days"] = res["remaining_days"]; save_config(self.cfg)
            self._log(f"✅ License hợp lệ — còn {res['remaining_days']} ngày"); self._refresh()
        else:
            self.sin.setText(f"❌ {res.get('message','Hết hạn')}"); self.sdot.setStyleSheet("color: #ef4444; font-size: 16px;"); self.btn_rn.setVisible(True)
            self._log(f"❌ License: {res.get('message','Hết hạn')}")

    def _license_dlg(self):
        d = LicenseDialog()
        d.exec()
        if d.result_data: self.cfg = d.result_data; self._check_license()

    # ----- Task -----
    def _task(self):
        url = self.iu.text().strip()
        if not url: QMessageBox.warning(self, "Lỗi", "Nhập URL video"); return
        sp = float(self.cb.currentText().replace("x",""))
        data = {"source_url": url, "license_key": self.cfg.get("license_key",""), "options": {
            "mirror": self.cm.isChecked(), "speed": sp, "blur_padding": self.cb2.isChecked(),
            "watermark_url": "logo.png" if self.cw2.isChecked() else None,
        }}
        self.bt.setEnabled(False); self.bt.setText("Đang gửi...")
        self._log(f"📤 Gửi yêu cầu dịch: {url[:60]}...")
        res = api_call("POST", "/translate", data)
        self.bt.setEnabled(True); self.bt.setText("Dịch ngay")
        if "error" in res:
            self._log(f"❌ Lỗi: {res['error']}")
            QMessageBox.warning(self, "Lỗi", res["error"])
        else:
            self._add_task(res["task_id"]); self.iu.clear()
            self._log(f"✅ Task #{res['task_id']} đã tạo")

    def _add_task(self, tid):
        cfg = load_config(); ts = cfg.get("tasks", [])
        ts.insert(0, {"id": tid, "status": "PENDING", "translated_url": None})
        cfg["tasks"] = ts[:50]; save_config(cfg); self._refresh()

    def _refresh(self):
        ts = load_config().get("tasks", [])
        if not ts: self.tc.setText("0 task"); return
        cleaned = []
        for t in ts:
            tid = t.get("id") or t.get("task_id")
            if not tid: continue
            cleaned.append(t)
            r = api_call("GET", f"/status/{tid}")
            if "error" not in r:
                old_st = t.get("status")
                t.update(r)
                new_st = r.get("status")
                if new_st != old_st and new_st:
                    self._log(f"{STATUS_ICON.get(new_st,'')} Task #{tid}: {STATUS_VN.get(new_st, new_st)}")
                self._update_row(r)
        cfg = load_config(); cfg["tasks"] = cleaned; save_config(cfg)
        done = sum(1 for t in cleaned if t.get("status")=="COMPLETED")
        fail = sum(1 for t in cleaned if t.get("status")=="FAILED")
        self.tc.setText(f"{len(cleaned)} task ({done}✅ {fail}❌)")

    def _update_row(self, t):
        tid = t["task_id"]
        for r in range(self.tb.rowCount()):
            if self.tb.item(r,0) and self.tb.item(r,0).text()==str(tid): break
        else:
            r = self.tb.rowCount(); self.tb.insertRow(r); self.tb.setItem(r,0,QTableWidgetItem(str(tid)))
        s = t.get("status","UNKNOWN")
        si = QTableWidgetItem(f"{STATUS_ICON.get(s,'⏳')} {STATUS_VN.get(s, s.replace('_',' ').title())}")
        if s=="COMPLETED": si.setForeground(QBrush(QColor("#4ade80")))
        elif s=="FAILED": si.setForeground(QBrush(QColor("#f87171")))
        self.tb.setItem(r,1,si); self.tb.setItem(r,2,QTableWidgetItem(f"#{tid} — {t.get('created_at','')[:19] if t.get('created_at') else ''}"))
        self.tb.setItem(r,3,QTableWidgetItem(t.get('progress','')[:25] if t.get('progress') else ''))
        url = t.get("translated_url","")
        if url:
            btn = QTableWidgetItem("▶ Mở video")
            btn.setForeground(QBrush(QColor("#60a5fa")))
            btn.setData(Qt.ItemDataRole.UserRole, url)
        else:
            btn = QTableWidgetItem("-")
        self.tb.setItem(r,4,btn)
        self.tb.sortByColumn(0, Qt.SortOrder.DescendingOrder)

    def _on_cell_clicked(self, row, col):
        if col == 4:
            item = self.tb.item(row, col)
            if item and item.data(Qt.ItemDataRole.UserRole):
                url = item.data(Qt.ItemDataRole.UserRole)
                self._log(f"🌐 Mở video: {url[:60]}...")
                webbrowser.open(url)

    # ----- Legacy -----
    def _show_error(self, msg): QMessageBox.warning(self, "Lỗi", msg)
    def _show_info(self, msg): self._log(msg)


CRASH_LOG = Path.home() / ".dichaudio" / "crash.log"

def main():
    try: _main()
    except SystemExit: raise
    except Exception:
        import traceback
        CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        CRASH_LOG.write_text(traceback.format_exc(), encoding="utf-8")
        try:
            _ = QApplication(sys.argv)
            QMessageBox.critical(None, "Lỗi", f"App crashed!\nXem log: {CRASH_LOG}")
        except: pass
        raise

def _main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion"); app.setFont(QFont("Segoe UI", 10))
    health = api_call("GET", "/health")
    if "error" in health:
        QMessageBox.critical(None, "Lỗi kết nối", f"❌ {health['error']}\n\nChạy: uvicorn server.main:app --reload --port 8002")
        return
    if not HAVE_PYQT:
        QMessageBox.critical(None, "Lỗi", "PyQt6 chưa được cài.\nCài: pip install PyQt6"); return
    Dashboard().show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
