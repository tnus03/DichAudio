"""
Celery Tasks — Xử lý video nền.
Worker nhận task_id và chạy pipeline, cập nhật database trực tiếp.
"""
import logging
from datetime import datetime

from celery import Task

from server.celery_app import celery_app
from server.database import SyncSessionLocal
from server.models import TranslationTask, TaskStatus
from server.core.pipeline import PipelineOrchestrator

logger = logging.getLogger(__name__)


class DatabaseTask(Task):
    """Base task có tích hợp database session."""
    _session = None

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Dọn session sau khi task hoàn thành."""
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass


def update_task_status(task_id: int, status: str, **extra):
    """
    Callback để pipeline cập nhật status vào database.
    Được gọi từ PipelineOrchestrator qua synchronous session.
    """
    session = SyncSessionLocal()
    try:
        task = session.query(TranslationTask).filter(
            TranslationTask.id == task_id
        ).first()
        if not task:
            logger.error(f"Task {task_id} không tồn tại trong DB.")
            return

        task.status = TaskStatus(status)

        if "translated_url" in extra:
            task.translated_url = extra["translated_url"]
        if "error_message" in extra:
            task.error_message = extra["error_message"]

        task.updated_at = datetime.utcnow()
        session.commit()

        logger.info(f"📝 DB Updated: Task {task_id} → {status}")
    except Exception as e:
        logger.error(f"Lỗi update database: {e}")
        session.rollback()
    finally:
        session.close()


def retry_failed_task(task_id: int) -> bool:
    """
    Retry một task bị FAILED. Reset status → PENDING, xoá error_message, chạy lại.
    Returns True nếu retry thành công, False nếu task không tồn tại hoặc không phải FAILED.
    """
    import traceback
    session = SyncSessionLocal()
    try:
        task = session.query(TranslationTask).filter(
            TranslationTask.id == task_id
        ).first()
        if not task:
            logger.warning(f"Task {task_id} không tồn tại.")
            return False
        if task.status != TaskStatus.FAILED:
            logger.warning(f"Task {task_id} không phải FAILED (status={task.status}).")
            return False

        # Reset task
        task.status = TaskStatus.PENDING
        task.error_message = None
        task.updated_at = datetime.utcnow()
        session.commit()
        task_id_val = task.id
        source_url = task.source_url
        options = task.options or {}
    except Exception as e:
        logger.error(f"Lỗi reset task {task_id}: {e}")
        return False
    finally:
        session.close()

    # Chạy lại pipeline trong thread
    import threading
    provider = options.get("translation_provider", "gemini")
    orch = PipelineOrchestrator(translation_provider=provider)
    orch.set_status_callback(update_task_status)

    def _run():
        try:
            orch.process_video(
                task_id=task_id_val,
                source_url=source_url,
                options=options,
            )
        except Exception as e:
            logger.error(f"❌ Retry task {task_id_val} thất bại: {e}")
            update_task_status(task_id_val, "FAILED", error_message=str(e))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info(f"🔄 Retry task {task_id} started")
    return True


def retry_all_failed_tasks() -> int:
    """Retry tất cả tasks FAILED. Returns số lượng đã retry."""
    session = SyncSessionLocal()
    try:
        failed_tasks = session.query(TranslationTask).filter(
            TranslationTask.status == TaskStatus.FAILED
        ).all()
        count = 0
        for task in failed_tasks:
            if retry_failed_task(task.id):
                count += 1
        return count
    finally:
        session.close()


@celery_app.task(
    base=DatabaseTask,
    bind=True,
    name="process_video_task",
    max_retries=2,
    default_retry_delay=60,
)
def process_video_task(self, task_id: int, source_url: str, options: dict = None):
    """
    [Celery Task] Xử lý video từ đầu đến cuối.
    Args:
        task_id: ID trong bảng translation_tasks
        source_url: URL video nguồn
        options: Tùy chọn chỉnh sửa (mirror, speed, watermark, ...)
    """
    logger.info(f"🚀 Bắt đầu xử lý task {task_id}: {source_url[:80]}...")

    # Khởi tạo orchestrator với provider từ options
    provider = (options or {}).get("translation_provider", "gemini")
    orchestrator = PipelineOrchestrator(translation_provider=provider)
    orchestrator.set_status_callback(update_task_status)

    try:
        # Chạy pipeline
        translated_url = orchestrator.process_video(
            task_id=task_id,
            source_url=source_url,
            options=options or {},
        )

        if translated_url:
            logger.info(f"✅ Task {task_id} hoàn thành: {translated_url}")
        else:
            logger.warning(f"⚠️ Task {task_id} hoàn thành nhưng không có URL upload.")

        return {
            "task_id": task_id,
            "success": bool(translated_url),
            "translated_url": translated_url,
        }

    except Exception as e:
        logger.error(f"❌ Task {task_id} lỗi: {e}")

        # Cập nhật status FAILED
        update_task_status(task_id, "FAILED", error_message=str(e))

        # Retry nếu chưa quá số lần
        try:
            raise self.retry(exc=e)
        except Exception:
            return {
                "task_id": task_id,
                "success": False,
                "error": str(e),
            }
