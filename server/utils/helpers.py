"""
Các hàm tiện ích: sinh HWID, sinh License Key, xử lý timestamps, v.v.
"""
import hashlib
import platform
import uuid
import subprocess
import re
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def generate_hwid() -> str:
    """
    Tạo mã định danh phần cứng (HWID) duy nhất cho Device Lock.
    Dựa trên: CPU serial, motherboard serial, MAC address.
    Trả về: SHA-256 hash dài 64 ký tự.
    """
    components = []
    try:
        # Windows: lấy thông tin qua WMIC
        if platform.system() == "Windows":
            # CPU Serial
            cpu = subprocess.run(
                "wmic cpu get processorid",
                capture_output=True, text=True, shell=True, timeout=5
            )
            if cpu.returncode == 0:
                lines = cpu.stdout.strip().split("\n")
                if len(lines) > 1:
                    components.append(lines[1].strip())

            # Motherboard Serial
            mb = subprocess.run(
                "wmic baseboard get serialnumber",
                capture_output=True, text=True, shell=True, timeout=5
            )
            if mb.returncode == 0:
                lines = mb.stdout.strip().split("\n")
                if len(lines) > 1:
                    components.append(lines[1].strip())

            # MAC Address (primary)
            mac = subprocess.run(
                "wmic nic where 'NetEnabled=True' get MACAddress",
                capture_output=True, text=True, shell=True, timeout=5
            )
            if mac.returncode == 0:
                lines = mac.stdout.strip().split("\n")
                for line in lines:
                    mac_addr = line.strip()
                    if mac_addr and re.match(r"^([0-9A-Fa-f]{2}[:-]){5}", mac_addr):
                        components.append(mac_addr)
                        break

        # Disk Serial (cross-platform fallback)
        try:
            if platform.system() == "Windows":
                disk = subprocess.run(
                    "wmic diskdrive get serialnumber",
                    capture_output=True, text=True, shell=True, timeout=5
                )
                if disk.returncode == 0:
                    lines = disk.stdout.strip().split("\n")
                    if len(lines) > 1:
                        components.append(lines[1].strip())
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"Không thể đọc HWID đầy đủ: {e}")

    # Fallback: dùng node của UUID (MAC ngẫu nhiên nếu không có thật)
    if not components:
        fallback = uuid.uuid1().node  # 48-bit MAC-based
        components.append(str(fallback))

    raw = "|".join(components)
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_license_key() -> str:
    """
    Sinh mã License Key ngẫu nhiên định dạng: XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
    Sử dụng UUID4 đảm bảo tính duy nhất và không thể đoán trước.
    """
    return str(uuid.uuid4()).upper()


def format_timestamp(seconds: float) -> str:
    """Chuyển đổi giây → định dạng HH:MM:SS,mmm (dùng cho SRT/FFmpeg)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_timestamp(ts: str) -> float:
    """Chuyển định dạng HH:MM:SS,mmm → số giây."""
    match = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)", ts)
    if not match:
        return 0.0
    h, m, s, ms = map(int, match.groups())
    return h * 3600 + m * 60 + s + ms / 1000


def calculate_expiry(duration_days: int) -> datetime:
    """Tính ngày hết hạn từ thời điểm hiện tại."""
    return datetime.utcnow() + timedelta(days=duration_days)


def slugify_filename(url: str) -> str:
    """Tạo tên file an toàn từ URL."""
    safe = re.sub(r"[^\w\-_]", "_", url)
    return safe[:100] or "video"
