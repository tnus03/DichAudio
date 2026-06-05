"""
SQLAlchemy ORM Models: User, LicenseKey, TranslationTask.
Hỗ trợ SQLite (dev) và MySQL (prod) thông qua cấu hình database.py.
"""
import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum, Float,
    ForeignKey, JSON, Index
)
from sqlalchemy.orm import relationship

from server.database import Base


class LicenseStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    ACTIVATED = "ACTIVATED"
    EXPIRED = "EXPIRED"


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    DOWNLOADING = "DOWNLOADING"
    EXTRACTING_AUDIO = "EXTRACTING_AUDIO"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSLATING = "TRANSLATING"
    GENERATING_VOICE = "GENERATING_VOICE"
    EDITING_AND_MERGING = "EDITING_AND_MERGING"
    UPLOADING = "UPLOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(String(64), unique=True, nullable=False, index=True)
    username = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    license_keys = relationship("LicenseKey", back_populates="user", lazy="dynamic")
    translation_tasks = relationship("TranslationTask", back_populates="user", lazy="dynamic")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id})>"


class LicenseKey(Base):
    __tablename__ = "license_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_code = Column(String(64), unique=True, nullable=False, index=True)
    duration_days = Column(Integer, nullable=False, default=30)
    status = Column(
        Enum(LicenseStatus),
        default=LicenseStatus.AVAILABLE,
        nullable=False,
        index=True
    )
    # Device ID được hash SHA-256 trước khi lưu (bảo mật)
    device_id = Column(String(128), nullable=True)
    activated_at = Column(DateTime, nullable=True)
    expired_at = Column(DateTime, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    user = relationship("User", back_populates="license_keys")

    __table_args__ = (
        Index("idx_license_key_status", "key_code", "status"),
    )

    def __repr__(self):
        return f"<LicenseKey(key={self.key_code[:8]}..., status={self.status})>"


class TranslationTask(Base):
    __tablename__ = "translation_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Input / Output URLs
    source_url = Column(String(2048), nullable=False)
    translated_url = Column(String(2048), nullable=True)  # Cloudinary URL

    # File paths (nội bộ server)
    video_path = Column(String(512), nullable=True)
    audio_path = Column(String(512), nullable=True)

    # Trạng thái xử lý
    status = Column(
        Enum(TaskStatus),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True
    )

    # Tùy chọn chỉnh sửa video (lưu dạng JSON)
    options = Column(JSON, nullable=True, default=dict)

    # Lỗi (nếu có)
    error_message = Column(Text, nullable=True)

    # Thời gian
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="translation_tasks")

    __table_args__ = (
        Index("idx_task_user_status", "user_id", "status"),
    )

    def __repr__(self):
        return f"<TranslationTask(id={self.id}, status={self.status})>"
