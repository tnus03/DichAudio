"""
Cấu hình hệ thống — đọc từ biến môi trường (.env) với giá trị mặc định cho development.
Hỗ trợ chuyển đổi linh hoạt SQLite (dev) ↔ MySQL (prod).
"""
import os
from pathlib import Path
from dotenv import load_dotenv, dotenv_values

# Load .env — KHÔNG ghi đè biến môi trường hệ thống
load_dotenv(override=False)

# Đọc riêng từ file .env (không bị ảnh hưởng bởi system env)
_env_vars = dotenv_values()  # Chỉ đọc từ .env file

# ---------- ĐƯỜNG DẪN ----------
BASE_DIR = Path(__file__).resolve().parent.parent
MEDIA_DIR = BASE_DIR / "media"
LOG_DIR = BASE_DIR / "logs"

# Tự động tạo thư mục nếu chưa tồn tại
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ---------- DATABASE ----------
# Hỗ trợ 2 format:
#   1. DATABASE_URL ưu tiên (từ .env)
#   2. DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
# KHÔNG đọc DATABASE_URL từ system env (tránh xung đột Neon/PostgreSQL)

_raw_db_url = _env_vars.get("DATABASE_URL", "")
if _raw_db_url:
    DATABASE_URL = _raw_db_url
else:
    _db_host = _env_vars.get("DB_HOST", "")
    if _db_host and _db_host not in ("", "mysql"):
        _db_port = _env_vars.get("DB_PORT", "3306")
        _db_user = _env_vars.get("DB_USER", "root")
        _db_pass = _env_vars.get("DB_PASSWORD", "")
        _db_name = _env_vars.get("DB_NAME", "dichaudio")
        DATABASE_URL = f"mysql+asyncmy://{_db_user}:{_db_pass}@{_db_host}:{_db_port}/{_db_name}"
    else:
        DATABASE_URL = f"sqlite+aiosqlite:///{BASE_DIR}/dichaudio.db"

# ---------- REDIS (Celery Broker) ----------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

# ---------- API KEYS ----------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ---------- CLOUDINARY ----------
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")

# ---------- TELEGRAM BOT ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0"))  # Chat ID nhóm Admin
# Proxy cho Telegram API (cần nếu ở VN/CN không truy cập được api.telegram.org)
# Định dạng: socks5://user:pass@host:port hoặc http://host:port
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "")
# Proxy riêng cho TTS (Edge-TTS), fallback sang TELEGRAM_PROXY_URL nếu không set
TTS_PROXY_URL = os.getenv("TTS_PROXY_URL", "") or TELEGRAM_PROXY_URL

# ---------- CÀI ĐẶT MẶC ĐỊNH ----------
# STT
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")  # tiny/base/small/medium/large-v3
USE_OPENAI_WHISPER_API = os.getenv("USE_OPENAI_WHISPER_API", "false").lower() == "true"

# TTS
TTS_VOICE = os.getenv("TTS_VOICE", "vi-VN-NamMinhNeural")  # Giọng Nam Minh
TTS_VOICE_FALLBACK = os.getenv("TTS_VOICE_FALLBACK", "vi-VN-HoaiMyNeural")

# Cấu hình lách bản quyền (mặc định)
DEFAULT_MIRROR = False
DEFAULT_SPEED = 1.0  # 1.05 hoặc 1.1
DEFAULT_ORIGINAL_VOLUME = 0.1  # Hạ âm gốc còn 10%
DEFAULT_BLUR_PADDING = False

# ---------- LICENSE ----------
LICENSE_DURATIONS = {
    "1_day": 1,
    "1_month": 30,
    "2_months": 60,
    "3_months": 90,
}

# ---------- LOGGING ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
