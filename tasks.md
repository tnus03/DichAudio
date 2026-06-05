# 🎯 Task List — Automated Video Translator & Reup Optimizer

## Phase 1: Thiết Lập Dự Án
- [x] Tạo cấu trúc thư mục (server/, client/)
- [x] Viết requirements.md — Yêu cầu hệ thống
- [x] Viết tasks.taskmd — Task list này
- [x] Viết requirements.txt — Python dependencies

## Phase 2: Database Layer
- [ ] Viết server/config.py — Cấu hình biến môi trường
- [ ] Viết server/database.py — SQLAlchemy engine & session
- [ ] Viết server/models.py — ORM models (User, LicenseKey, TranslationTask)
- [ ] Viết server/schemas.py — Pydantic schemas

## Phase 3: Core AI Pipeline
- [ ] Viết server/utils/helpers.py — Utility functions (HWID, key gen)
- [ ] Viết server/core/stt.py — faster-whisper transcription
- [ ] Viết server/core/translator.py — Gemini 1.5 Flash translation
- [ ] Viết server/core/tts.py — Edge-TTS voice generation
- [ ] Viết server/core/video_editor.py — FFmpeg video editing
- [ ] Viết server/core/pipeline.py — Pipeline orchestrator

## Phase 4: Task Queue & API
- [ ] Viết server/celery_app.py — Celery app configuration
- [ ] Viết server/tasks/video_tasks.py — Celery video processing task
- [ ] Viết server/api/translate.py — Translation endpoints
- [ ] Viết server/api/license.py — License management endpoints
- [ ] Viết server/main.py — FastAPI app entry point

## Phase 5: Telegram Bot
- [ ] Viết server/bot/bot.py — Bot handlers & admin flow
- [ ] Viết server/bot/__main__.py — Bot entry point

## Phase 6: Kiểm Thử
- [ ] Kiểm tra server: uvicorn server.main:app --reload
- [ ] Kiểm tra Celery worker
- [ ] Kiểm tra Bot Telegram
- [ ] Test API endpoints với curl
