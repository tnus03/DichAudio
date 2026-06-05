"""
Script độc lập — Lấy mã định danh phần cứng (HWID / Device ID).
Chạy trên máy người dùng (Windows), không cần cài thêm thư viện.
Kết quả: Mã SHA-256 dài 64 ký tự, dùng để kích hoạt License Key.

Cách dùng:
  python get_hwid.py
"""
import hashlib
import platform
import subprocess
import uuid
import re


def get_hwid() -> str:
    """
    Tạo HWID dựa trên: CPU Serial + Motherboard Serial + MAC Address + Disk Serial.
    Trả về: SHA-256 hex string (64 ký tự).
    """
    components = []

    try:
        # 1. CPU Serial
        cpu = subprocess.run(
            "wmic cpu get processorid",
            capture_output=True, text=True, shell=True, timeout=5
        )
        if cpu.returncode == 0:
            lines = cpu.stdout.strip().split("\n")
            if len(lines) > 1:
                val = lines[1].strip()
                if val:
                    components.append(val)

        # 2. Motherboard Serial
        mb = subprocess.run(
            "wmic baseboard get serialnumber",
            capture_output=True, text=True, shell=True, timeout=5
        )
        if mb.returncode == 0:
            lines = mb.stdout.strip().split("\n")
            if len(lines) > 1:
                val = lines[1].strip()
                if val:
                    components.append(val)

        # 3. MAC Address (primary network)
        mac = subprocess.run(
            "wmic nic where 'NetEnabled=True' get MACAddress",
            capture_output=True, text=True, shell=True, timeout=5
        )
        if mac.returncode == 0:
            lines = mac.stdout.strip().split("\n")
            for line in lines:
                m = line.strip()
                if m and re.match(r"^([0-9A-Fa-f]{2}[:-]){5}", m):
                    components.append(m)
                    break

        # 4. Disk Serial
        disk = subprocess.run(
            "wmic diskdrive get serialnumber",
            capture_output=True, text=True, shell=True, timeout=5
        )
        if disk.returncode == 0:
            lines = disk.stdout.strip().split("\n")
            if len(lines) > 1:
                val = lines[1].strip()
                if val:
                    components.append(val)

    except Exception:
        pass

    # Fallback: dùng UUID node (MAC-based)
    if not components:
        components.append(str(uuid.uuid1().node))

    raw = "|".join(components)
    return hashlib.sha256(raw.encode()).hexdigest()


if __name__ == "__main__":
    print("=" * 64)
    print("  DichAudio — HWID Generator")
    print("  Dùng mã này để kích hoạt License Key")
    print("=" * 64)
    print()
    print(f"  Hệ điều hành: {platform.system()} {platform.release()}")
    print(f"  Máy tính:     {platform.node()}")
    print()
    print(f"  ▶ Device ID:  {get_hwid()}")
    print()
    print("=" * 64)
