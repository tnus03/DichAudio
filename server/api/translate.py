"""
API Router — Quản lý task dịch thuật.
Endpoints: POST /translate, GET /status/{task_id}
"""
import logging
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_async_session
from server.models import TranslationTask, TaskStatus, LicenseKey, LicenseStatus
from server.schemas import (
    TranslateRequest,
    TranslateResponse,
    TaskStatusResponse,
    VideoOptions,
)
from server.tasks.video_tasks import process_video_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Translation"])


@router.post("/translate", response_model=TranslateResponse)
async def create_translation_task(
    request: TranslateRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Tạo task dịch video mới.
    1. Kiểm tra License Key còn hạn
    2. Tạo TranslationTask trong DB
    3. Gửi Celery task
    """
    # 1. Kiểm tra License Key
    from sqlalchemy import select

    result = await session.execute(
        select(LicenseKey).where(
            LicenseKey.key_code == request.license_key,
            LicenseKey.status == LicenseStatus.ACTIVATED,
        )
    )
    license_key = result.scalar_one_or_none()

    if not license_key:
        # Kiểm tra key AVAILABLE (chưa kích hoạt)
        result = await session.execute(
            select(LicenseKey).where(
                LicenseKey.key_code == request.license_key,
                LicenseKey.status == LicenseStatus.AVAILABLE,
            )
        )
        license_key = result.scalar_one_or_none()
        if license_key:
            raise HTTPException(
                status_code=403,
                detail="License Key chưa được kích hoạt. Vui lòng kích hoạt trước."
            )
        raise HTTPException(
            status_code=404,
            detail="License Key không hợp lệ."
        )

    # Kiểm tra hết hạn
    if license_key.expired_at and license_key.expired_at < datetime.utcnow():
        raise HTTPException(
            status_code=403,
            detail="License Key đã hết hạn. Vui lòng gia hạn."
        )

    # 2. Parse options
    opts = request.options or VideoOptions()
    options_dict = {
        "mirror": opts.mirror,
        "speed": opts.speed,
        "blur_padding": opts.blur_padding,
        "blur_intensity": opts.blur_intensity,
        "watermark_url": opts.watermark_url,
        "watermark_position": opts.watermark_position,
        "watermark_scale": opts.watermark_scale,
        "original_volume": opts.original_volume,
        "subtitles": opts.subtitles,
        "subtitle_font_size": opts.subtitle_font_size,
        "subtitle_position": opts.subtitle_position,
        "subtitle_color": opts.subtitle_color,
        "bg_music": opts.bg_music,
        "bg_music_volume": opts.bg_music_volume,
        "dubbed_volume": opts.dubbed_volume,
        "translation_provider": opts.translation_provider,
        "brightness": opts.brightness,
        "contrast": opts.contrast,
        "saturation": opts.saturation,
        "rotate": opts.rotate,
        "crop_top": opts.crop_top,
        "crop_bottom": opts.crop_bottom,
        "crop_left": opts.crop_left,
        "crop_right": opts.crop_right,
        "custom_audio": opts.custom_audio,
        "target_language": opts.target_language,
        "voice_gender": opts.voice_gender,
    }

    # 3. Tạo TranslationTask
    task = TranslationTask(
        user_id=license_key.user_id,
        source_url=request.source_url,
        status=TaskStatus.PENDING,
        options=options_dict,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(task)
    await session.flush()
    await session.refresh(task)
    task_id = task.id

    if hasattr(session, 'commit'):
        await session.commit()

    logger.info(f"📝 Task {task_id} created: {request.source_url[:80]}...")

    # 4. Gửi Celery task (fire-and-forget) với fallback chạy trực tiếp
    celery_sent = False
    try:
        process_video_task.delay(
            task_id=task_id,
            source_url=request.source_url,
            options=options_dict,
        )
        celery_sent = True
    except Exception as e:
        logger.warning(f"⚠️ Celery không khả dụng ({e}), chạy pipeline trực tiếp...")

    if not celery_sent:
        # Fallback: chạy pipeline đồng bộ trong thread
        import threading
        from server.core.pipeline import PipelineOrchestrator
        from server.tasks.video_tasks import update_task_status

        def _run_pipeline():
            import logging
            logger = logging.getLogger(__name__)
            try:
                provider = options_dict.get("translation_provider", "gemini")
                orch = PipelineOrchestrator(translation_provider=provider)
                orch.set_status_callback(update_task_status)
                orch.process_video(
                    task_id=task_id,
                    source_url=request.source_url,
                    options=options_dict,
                )
            except Exception as e:
                logger.error(f"❌ Pipeline fallback error: {e}")
                update_task_status(task_id, "FAILED", error_message=str(e))

        thread = threading.Thread(target=_run_pipeline, daemon=True)
        thread.start()
        logger.info(f"🔄 Pipeline fallback started for task {task_id}")

    return TranslateResponse(
        task_id=task_id,
        status=TaskStatus.PENDING.value,
        message="Task đã được tạo và đang xử lý.",
    )


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Lấy trạng thái hiện tại của task dịch.
    Dashboard poll endpoint này để hiển thị progress bar.
    """
    from sqlalchemy import select

    result = await session.execute(
        select(TranslationTask).where(TranslationTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} không tồn tại."
        )

    # Map status → progress text
    progress_map = {
        TaskStatus.PENDING: "Đang chờ xử lý...",
        TaskStatus.DOWNLOADING: "Đang tải video...",
        TaskStatus.EXTRACTING_AUDIO: "Đang tách âm thanh...",
        TaskStatus.TRANSCRIBING: "Đang nhận diện giọng nói...",
        TaskStatus.TRANSLATING: "Đang dịch thuật...",
        TaskStatus.GENERATING_VOICE: "Đang tạo giọng đọc...",
        TaskStatus.EDITING_AND_MERGING: "Đang ghép video...",
        TaskStatus.UPLOADING: "Đang tải lên Cloudinary...",
        TaskStatus.COMPLETED: "Hoàn thành!",
        TaskStatus.FAILED: "Thất bại.",
    }

    return TaskStatusResponse(
        task_id=task.id,
        status=task.status.value,
        progress=progress_map.get(task.status, "Đang xử lý..."),
        translated_url=task.translated_url,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/tasks", response_model=list[TaskStatusResponse])
async def list_tasks(
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Lấy danh sách tasks gần đây (không cần xác thực — dành cho development).
    """
    from sqlalchemy import select, desc

    result = await session.execute(
        select(TranslationTask)
        .order_by(desc(TranslationTask.created_at))
        .offset(offset)
        .limit(limit)
    )
    tasks = result.scalars().all()

    progress_map = {
        TaskStatus.PENDING: "Đang chờ xử lý...",
        TaskStatus.DOWNLOADING: "Đang tải video...",
        TaskStatus.EXTRACTING_AUDIO: "Đang tách âm thanh...",
        TaskStatus.TRANSCRIBING: "Đang nhận diện giọng nói...",
        TaskStatus.TRANSLATING: "Đang dịch thuật...",
        TaskStatus.GENERATING_VOICE: "Đang tạo giọng đọc...",
        TaskStatus.EDITING_AND_MERGING: "Đang ghép video...",
        TaskStatus.UPLOADING: "Đang tải lên Cloudinary...",
        TaskStatus.COMPLETED: "Hoàn thành!",
        TaskStatus.FAILED: "Thất bại.",
    }

    return [
        TaskStatusResponse(
            task_id=t.id,
            status=t.status.value,
            progress=progress_map.get(t.status, "Đang xử lý..."),
            translated_url=t.translated_url,
            error_message=t.error_message,
            created_at=t.created_at,
            updated_at=t.updated_at,
        ) for t in tasks
    ]


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Retry một task FAILED.
    Reset status → PENDING và chạy lại pipeline.
    """
    from sqlalchemy import select
    result = await session.execute(
        select(TranslationTask).where(TranslationTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} không tồn tại.")
    if task.status != TaskStatus.FAILED:
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} không phải FAILED (status={task.status.value})."
        )

    # Retry qua sync function
    from server.tasks.video_tasks import retry_failed_task
    ok = retry_failed_task(task_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Không thể retry task.")

    return {
        "task_id": task_id,
        "status": "PENDING",
        "message": f"Task #{task_id} đang được retry.",
    }


@router.post("/tasks/retry-all")
async def retry_all_failed():
    """Retry tất cả tasks FAILED."""
    from server.tasks.video_tasks import retry_all_failed_tasks
    count = retry_all_failed_tasks()
    return {
        "retried": count,
        "message": f"Đã retry {count} task(s).",
    }


@router.post("/upload", tags=["Upload"])
async def upload_video(
    file: UploadFile = File(...),
    license_key: str = Form(...),
    mirror: bool = Form(False),
    speed: float = Form(1.0),
    blur_padding: bool = Form(False),
    translation_provider: str = Form("auto"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Upload video từ máy tính lên để xử lý.
    Dùng multipart/form-data: file + license_key + options.
    """
    import aiofiles
    from server.tasks.video_tasks import process_video_task, update_task_status
    from server.core.pipeline import PipelineOrchestrator

    # Check license
    from sqlalchemy import select
    result = await session.execute(
        select(LicenseKey).where(
            LicenseKey.key_code == license_key,
            LicenseKey.status == LicenseStatus.ACTIVATED,
        )
    )
    license_key_obj = result.scalar_one_or_none()
    if not license_key_obj:
        raise HTTPException(status_code=403, detail="License Key không hợp lệ hoặc chưa kích hoạt.")
    if license_key_obj.expired_at and license_key_obj.expired_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="License Key đã hết hạn.")

    # Save uploaded file
    from server.config import MEDIA_DIR
    upload_dir = MEDIA_DIR / "uploads"
    upload_dir.mkdir(exist_ok=True)

    safe_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = str(upload_dir / safe_name)

    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    file_size = os.path.getsize(file_path)
    logger.info(f"📤 Upload: {file.filename} ({file_size} bytes) -> {file_path}")

    # Create task
    options_dict = {
        "mirror": mirror,
        "speed": speed,
        "blur_padding": blur_padding,
        "translation_provider": translation_provider,
        "source_file": file_path,  # Mark as local file
    }
    task = TranslationTask(
        user_id=license_key_obj.user_id,
        source_url=f"upload://{safe_name}",
        status=TaskStatus.PENDING,
        options=options_dict,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(task)
    await session.flush()
    await session.refresh(task)
    task_id = task.id
    await session.commit()

    # Run pipeline (fire-and-forget with fallback)
    def _run():
        try:
            provider = options_dict.get("translation_provider", "auto")
            orch = PipelineOrchestrator(translation_provider=provider)
            orch.set_status_callback(update_task_status)
            orch.process_video(task_id=task_id, source_url=file_path, options=options_dict)
        except Exception as e:
            logger.error(f"Upload task {task_id} error: {e}")
            update_task_status(task_id, "FAILED", error_message=str(e))

    import threading
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {
        "task_id": task_id,
        "status": "PENDING",
        "filename": file.filename,
        "size": file_size,
        "message": "Video đã được upload và đang xử lý.",
    }


@router.post("/merge", tags=["Merge"])
async def merge_video_audio(
    video: UploadFile = File(...),
    audio: UploadFile = File(...),
    license_key: str = Form(...),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Ghép video va audio. Upload ca 2 file, thay audio track cua video bang audio file.
    """
    from server.config import MEDIA_DIR

    # Check license
    from sqlalchemy import select
    result = await session.execute(
        select(LicenseKey).where(
            LicenseKey.key_code == license_key,
            LicenseKey.status == LicenseStatus.ACTIVATED,
        )
    )
    license_key_obj = result.scalar_one_or_none()
    if not license_key_obj:
        raise HTTPException(status_code=403, detail="License Key không hợp lệ.")

    # Save files
    merge_dir = MEDIA_DIR / "merge"
    merge_dir.mkdir(exist_ok=True)

    import aiofiles, uuid
    vid_path = str(merge_dir / f"{uuid.uuid4().hex}_{video.filename}")
    aud_path = str(merge_dir / f"{uuid.uuid4().hex}_{audio.filename}")
    out_path = str(merge_dir / f"merged_{uuid.uuid4().hex}.mp4")

    async with aiofiles.open(vid_path, "wb") as f:
        await f.write(await video.read())
    async with aiofiles.open(aud_path, "wb") as f:
        await f.write(await audio.read())

    # Merge
    from server.core.video_editor import VideoEditor
    editor = VideoEditor()
    try:
        editor.replace_audio(vid_path, aud_path, out_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ghép thất bại: {e}")

    return {
        "video": video.filename,
        "audio": audio.filename,
        "output": out_path,
        "size": os.path.getsize(out_path),
        "message": "Ghép video + audio thành công!",
    }


@router.post("/dub-video", tags=["Dub"])
async def dub_video(
    source_url: str = Form(...),
    target_video: UploadFile = File(...),
    license_key: str = Form(...),
    mirror: bool = Form(False),
    blur_padding: bool = Form(False),
    speed: float = Form(1.0),
    translation_provider: str = Form("auto"),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Lay audio tu source_url, dich va TTS, roi ghep vao target_video.
    """
    from server.config import MEDIA_DIR
    from server.tasks.video_tasks import update_task_status
    from server.core.pipeline import PipelineOrchestrator
    from server.core.video_editor import VideoEditor
    from sqlalchemy import select
    import aiofiles, uuid, shutil, json

    # Check license
    result = await session.execute(
        select(LicenseKey).where(
            LicenseKey.key_code == license_key,
            LicenseKey.status == LicenseStatus.ACTIVATED,
        )
    )
    lic = result.scalar_one_or_none()
    if not lic:
        raise HTTPException(status_code=403, detail="License Key không hợp lệ.")
    if lic.expired_at and lic.expired_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="License Key da het han.")

    # Tao task
    task = TranslationTask(
        user_id=lic.user_id, source_url=source_url,
        status=TaskStatus.PENDING, options={"translation_provider": translation_provider},
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    session.add(task); await session.flush(); await session.refresh(task)
    task_id = task.id; await session.commit()

    task_dir = MEDIA_DIR / f"task_{task_id}"; task_dir.mkdir(parents=True, exist_ok=True)

    # Luu target video
    target_path = str(task_dir / f"target_{uuid.uuid4().hex}_{target_video.filename}")
    async with aiofiles.open(target_path, "wb") as f:
        await f.write(await target_video.read())

    def run():
        try:
            # 1. Download source, STT, translate
            orch = PipelineOrchestrator(translation_provider=translation_provider)
            orch.set_status_callback(update_task_status)

            update_task_status(task_id, "DOWNLOADING")
            source_video = orch._download_video(source_url, task_dir)
            if not source_video:
                raise RuntimeError("Tai source video that bai")

            update_task_status(task_id, "EXTRACTING_AUDIO")
            audio_path = str(task_dir / "source_audio.wav")
            orch.editor.extract_audio(source_video, audio_path)

            update_task_status(task_id, "TRANSCRIBING")
            segments = orch.stt.transcribe(audio_path)
            if not segments:
                raise RuntimeError("Khong nhan dien duoc giong noi")

            update_task_status(task_id, "TRANSLATING")
            translated = orch.translator.translate(segments)

            update_task_status(task_id, "GENERATING_VOICE")
            dubbed = orch._generate_voices(translated, task_dir)

            # Chuan bi subtitle
            subtitles = [{"start": s["start"], "end": s["end"], "text": s.get("translated_text", "")}
                         for s in translated if s.get("translated_text", "").strip()]

            # 2. Ap dung vao target video
            update_task_status(task_id, "EDITING_AND_MERGING")
            opts = {"mirror": mirror, "speed": speed, "blur_padding": blur_padding,
                    "original_volume": 0.1, "subtitles": subtitles}
            result_path = orch._edit_video(target_path, dubbed, task_dir, opts)

            # 3. Upload
            update_task_status(task_id, "UPLOADING")
            url = orch._upload_to_cloudinary(result_path)
            update_task_status(task_id, "COMPLETED" if url else "FAILED",
                               translated_url=url or "",
                               error_message="" if url else "Upload that bai")

            # Cleanup
            shutil.rmtree(task_dir, ignore_errors=True)

        except Exception as e:
            logger.error(f"Dub task {task_id} error: {e}")
            update_task_status(task_id, "FAILED", error_message=str(e))

    import threading
    threading.Thread(target=run, daemon=True).start()

    return {"task_id": task_id, "status": "PENDING",
            "message": f"Dang xu ly source_url va ghep vao {target_video.filename}"}
