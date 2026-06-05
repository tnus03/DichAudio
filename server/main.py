"""
FastAPI Application — Entry Point.
Tích hợp: CORS, routers, health check, dashboard, khởi tạo database.
Tự động xử lý các task PENDING khi server khởi động.
"""
import logging
import sys
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config import LOG_LEVEL
from server.database import init_db
from server.api.translate import router as translate_router
from server.api.license import router as license_router

# ---------- LOGGING ----------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def _process_pending_tasks():
    """Tự động xử lý các task PENDING trong background (định kỳ 5s)."""
    import logging
    logger = logging.getLogger(__name__)
    time.sleep(5)
    logger.info("Background processor started (checking every 5s)")

    while True:
        try:
            from server.database import SyncSessionLocal
            from server.models import TranslationTask, TaskStatus
            from server.tasks.video_tasks import update_task_status
            from server.core.pipeline import PipelineOrchestrator

            session = SyncSessionLocal()
            try:
                tasks = session.query(TranslationTask).filter(
                    TranslationTask.status == TaskStatus.PENDING
                ).order_by(TranslationTask.id).all()
            finally:
                session.close()

            if tasks:
                logger.info(f"Tim thay {len(tasks)} task PENDING, bat dau xu ly...")

            for t in tasks:
                tid = t.id
                url = t.source_url
                opts = dict(t.options or {})
                opts.setdefault("whisper_model_size", "tiny")
                opts.setdefault("mirror", False)
                opts.setdefault("blur_padding", False)
                opts.setdefault("speed", 1.0)
                opts.setdefault("translation_provider", "auto")

                logger.info(f"Task #{tid}: {str(url)[:60]}...")
                try:
                    orch = PipelineOrchestrator(translation_provider=opts.get("translation_provider", "auto"))
                    orch.set_status_callback(update_task_status)
                    result = orch.process_video(task_id=tid, source_url=url, options=opts)
                    if result:
                        logger.info(f"Task #{tid} hoan thanh: {result[:60]}")
                    else:
                        logger.warning(f"Task #{tid} khong co URL upload")
                except Exception as e:
                    logger.error(f"Task #{tid} that bai: {e}")
                    update_task_status(tid, "FAILED", error_message=str(e))
                time.sleep(2)

        except Exception as e:
            logger.error(f"Background processor error: {e}")

        # Cleanup: xoa task cu hon 1 ngay
        try:
            from server.database import SyncSessionLocal
            from server.models import TranslationTask, TaskStatus
            from datetime import datetime, timedelta
            import os, shutil
            from server.config import MEDIA_DIR

            session = SyncSessionLocal()
            try:
                cutoff = datetime.utcnow() - timedelta(days=1)
                old_tasks = session.query(TranslationTask).filter(
                    TranslationTask.created_at < cutoff
                ).all()
                if old_tasks:
                    logger.info(f"Cleanup: xoa {len(old_tasks)} task cu...")
                    for t in old_tasks:
                        # Xoa media
                        task_dir = MEDIA_DIR / f"task_{t.id}"
                        if task_dir.exists():
                            shutil.rmtree(task_dir, ignore_errors=True)
                        # Xoa task record
                        session.delete(t)
                    session.commit()
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"Cleanup: {e}")

        time.sleep(5)  # Kiem tra moi 5 giay


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo database + tự động xử lý pending tasks khi app start."""
    logger.info("🚀 Đang khởi động DichAudio Server...")
    try:
        await init_db()
        logger.info("✅ Database ready.")
    except Exception as e:
        logger.warning(f"⚠️ Database init warning: {e}")

    # Chay background thread de xu ly pending tasks
    thread = threading.Thread(target=_process_pending_tasks, daemon=True)
    thread.start()

    # Chay Telegram Bot (neu co token)
    try:
        from server.config import TELEGRAM_BOT_TOKEN
        if TELEGRAM_BOT_TOKEN:
            from server.bot.bot import run_bot

            def _start_bot():
                try:
                    run_bot()
                except Exception as e:
                    logger.warning(f"Bot stopped: {e}")

            bot_thread = threading.Thread(target=_start_bot, daemon=True)
            bot_thread.start()
            logger.info("🤖 Telegram Bot started.")
        else:
            logger.info("Bot token not configured, skipping.")
    except Exception as e:
        logger.warning(f"Bot khong the khoi dong: {e}")

    yield
    logger.info("🛑 DichAudio Server đã dừng.")


app = FastAPI(
    title="DichAudio - Automated Video Translator",
    description=(
        "API dịch thuật và lồng tiếng video tự động. "
        "Hỗ trợ TikTok, Douyin, YouTube Shorts."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- ROUTERS ----------
app.include_router(translate_router)
app.include_router(license_router)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint."""
    return {"service": "DichAudio Server", "version": "1.0.0", "docs": "/docs"}


@app.get("/api/v1/health", tags=["System"])
async def health_check():
    """Health check endpoint — monitoring."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "service": "DichAudio Server",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.main:app", host="127.0.0.1", port=8002, reload=True)
