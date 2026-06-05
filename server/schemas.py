"""
Pydantic Schemas — Request/Response validation cho FastAPI endpoints.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl


# =====================
# TRANSLATION SCHEMAS
# =====================

class VideoOptions(BaseModel):
    """Tùy chọn chỉnh sửa video từ Dashboard."""
    # === Cơ bản ===
    mirror: bool = False
    speed: float = 1.0  # 0.5 - 2.0
    blur_padding: bool = False
    blur_intensity: float = 10.0  # Độ mờ viền (sigma: 1-50)
    watermark_url: Optional[str] = None
    watermark_position: str = "bottom_right"  # bottom_right, bottom_left, top_right, top_left
    watermark_scale: float = 0.1  # Tỷ lệ watermark (0.01 - 0.3)
    subtitles: bool = True
    subtitle_font_size: int = 24  # Cỡ chữ phụ đề
    subtitle_position: str = "bottom"  # bottom, top, middle
    subtitle_color: str = "white"  # white, yellow, red, etc.
    original_volume: float = 0.1  # 0.0 - 1.0

    # === Nâng cao ===
    brightness: float = 0.0  # Độ sáng (-1.0 to 1.0)
    contrast: float = 1.0  # Độ tương phản (0.0 - 3.0)
    saturation: float = 1.0  # Độ bão hòa (0.0 - 3.0)
    rotate: int = 0  # Xoay video (0, 90, 180, 270)
    crop_top: int = 0  # Cắt pixel từ trên
    crop_bottom: int = 0  # Cắt pixel từ dưới
    crop_left: int = 0  # Cắt pixel từ trái
    crop_right: int = 0  # Cắt pixel từ phải

    # === Audio ===
    bg_music: Optional[str] = None
    bg_music_volume: float = 0.05  # Âm lượng nhạc nền
    dubbed_volume: float = 1.0  # Âm lượng giọng dịch (0.0 - 1.0)
    custom_audio: Optional[str] = None  # Đường dẫn file audio thay thế

    # === AI ===
    translation_provider: str = "auto"
    target_language: str = "Vietnamese"  # Ngôn ngữ đích cho bản dịch
    voice_gender: str = "Nam"  # Nam hoặc Nữ


class TranslateRequest(BaseModel):
    """Yêu cầu dịch video mới."""
    source_url: str = Field(
        ..., min_length=1, max_length=2048,
        description="URL video (TikTok, Douyin, YouTube Shorts)"
    )
    license_key: str = Field(
        ..., min_length=1, max_length=64,
        description="License key để xác thực"
    )
    options: Optional[VideoOptions] = None


class TranslateResponse(BaseModel):
    """Phản hồi khi tạo task dịch thành công."""
    task_id: int
    status: str
    message: str = "Task đã được tạo và đang xử lý."


class TaskStatusResponse(BaseModel):
    """Trạng thái xử lý của một task."""
    task_id: int
    status: str
    progress: Optional[str] = None
    translated_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# =====================
# LICENSE SCHEMAS
# =====================

class LicenseActivateRequest(BaseModel):
    """Yêu cầu kích hoạt License Key."""
    license_key: str = Field(
        ..., min_length=1, max_length=64,
        description="Mã License Key"
    )
    device_id: str = Field(
        ..., min_length=1, max_length=256,
        description="Mã định danh phần cứng (HWID)"
    )
    telegram_id: Optional[str] = Field(
        None, max_length=64,
        description="ID Telegram (nếu có)"
    )


class LicenseActivateResponse(BaseModel):
    """Phản hồi kích hoạt License Key."""
    success: bool
    message: str
    expired_at: Optional[datetime] = None
    remaining_days: Optional[int] = None
    remaining_hours: Optional[int] = None


class LicenseCheckRequest(BaseModel):
    """Yêu cầu kiểm tra License Key."""
    license_key: str = Field(
        ..., min_length=1, max_length=64,
        description="Mã License Key"
    )
    device_id: str = Field(
        ..., min_length=1, max_length=256,
        description="Mã định danh phần cứng (HWID)"
    )


class LicenseCheckResponse(BaseModel):
    """Phản hồi kiểm tra License Key."""
    valid: bool
    message: str
    expired_at: Optional[datetime] = None
    remaining_days: Optional[int] = None
    remaining_hours: Optional[int] = None


# =====================
# HEALTH SCHEMA
# =====================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str = "1.0.0"
