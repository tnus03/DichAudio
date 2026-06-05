"""
Celery App — Cấu hình Task Queue với Redis làm Broker.
Worker chạy song song với FastAPI, xử lý các background tasks nặng.
"""
import logging
import sys
from pathlib import Path

# Đảm bảo thư mục gốc có trong sys.path (cho Celery worker)
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from celery import Celery

from server.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

logger = logging.getLogger(__name__)

celery_app = Celery(
    "dichaudio",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

# Cấu hình Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task settings
    task_track_started=True,
    task_acks_late=True,                # Re-deliver nếu worker crash
    worker_prefetch_multiplier=1,       # Mỗi worker xử lý 1 task 1 lần
    task_soft_time_limit=600,           # 10 phút soft limit
    task_time_limit=900,                # 15 phút hard limit
    broker_connection_retry_on_startup=True,  # Celery 6.x compat
    # Schedule
    beat_schedule={},                   # Không có scheduled tasks
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["server.tasks"])

# Import tasks để đăng ký với worker
import server.tasks.video_tasks  # noqa: F401
