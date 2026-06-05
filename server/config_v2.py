# -*- coding: utf-8 -*-
"""
TOML-based config — đọc từ config.toml, fallback .env
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Thử đọc TOML trước
_config = {}
_toml_path = BASE_DIR / "config.toml"
if _toml_path.exists():
    try:
        import tomllib  # Python 3.11+
        with open(_toml_path, "rb") as f:
            _config = tomllib.load(f)
    except (ImportError, tomllib.TOMLDecodeError):
        try:
            import tomli
            with open(_toml_path, "rb") as f:
                _config = tomli.load(f)
        except ImportError:
            pass

def _get(*keys, default=""):
    """Đọc từ TOML → env → default."""
    # Thử TOML
    c = _config
    for k in keys:
        if isinstance(c, dict):
            c = c.get(k, {})
        else:
            break
    if c not in ({}, None, ""):
        return c
    # Fallback env
    return os.getenv("_".join(keys).upper(), default)

# ── DATABASE ──
DATABASE_URL = _get("database", "url") or os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR}/dichaudio.db")

# ── REDIS ──
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

# ── AI PROVIDERS ──
TRANSLATION_PROVIDER = os.getenv("TRANSLATION_PROVIDER", "auto")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ── STT ──
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
USE_OPENAI_WHISPER_API = os.getenv("USE_OPENAI_WHISPER_API", "false").lower() == "true"

# ── TTS ──
TTS_VOICE = os.getenv("TTS_VOICE", "vi-VN-NamMinhNeural")
TTS_VOICE_FALLBACK = os.getenv("TTS_VOICE_FALLBACK", "vi-VN-HoaiMyNeural")

# ── CLOUDINARY ──
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")

# ── TELEGRAM ──
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0"))
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "")

# ── PATHS ──
MEDIA_DIR = BASE_DIR / "media"
LOG_DIR = BASE_DIR / "logs"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── DEFAULTS ──
DEFAULT_MIRROR = False
DEFAULT_SPEED = 1.0
DEFAULT_ORIGINAL_VOLUME = 0.1
DEFAULT_BLUR_PADDING = False

LICENSE_DURATIONS = {"1_day": 1, "1_month": 30, "2_months": 60, "3_months": 90}
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
