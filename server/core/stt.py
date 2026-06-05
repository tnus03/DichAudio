"""
Speech-to-Text (STT) Module.
Sử dụng faster-whisper (chạy local) hoặc OpenAI Whisper API.
Trả về danh sách các segment với timestamps chi tiết.
"""
import json
import logging
import os
from pathlib import Path
from typing import Optional

from server.config import WHISPER_MODEL_SIZE, USE_OPENAI_WHISPER_API, OPENAI_API_KEY

logger = logging.getLogger(__name__)

# Map model size → thư mục cache trên HuggingFace
MODEL_CACHE_DIRS = {
    "tiny": "models--Systran--faster-whisper-tiny",
    "base": "models--Systran--faster-whisper-base",
    "small": "models--Systran--faster-whisper-small",
    "medium": "models--Systran--faster-whisper-medium",
    "large-v3": "models--Systran--faster-whisper-large-v3",
}

# Dung lượng ước tính từng model
MODEL_ESTIMATED_SIZE = {
    "tiny": "~75 MB",
    "base": "~150 MB",
    "small": "~500 MB",
    "medium": "~1.5 GB",
    "large-v3": "~3 GB",
}


def _is_model_cached(model_size: str) -> bool:
    """Kiểm tra model đã được download về cache chưa."""
    cache_dir = MODEL_CACHE_DIRS.get(model_size)
    if not cache_dir:
        return False
    # HuggingFace cache thường ở ~/.cache/huggingface/hub/
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub" / cache_dir
    if hf_cache.exists():
        # Kiểm tra có file model thật (không chỉ lock)
        blobs = list(hf_cache.rglob("*.bin")) + list(hf_cache.rglob("*.safetensors"))
        return len(blobs) > 0
    return False


class WhisperSTT:
    """
    Nhận diện giọng nói, xuất văn bản kèm timestamps.
    Mặc định dùng faster-whisper chạy local.
    Nếu USE_OPENAI_WHISPER_API=true, dùng OpenAI Whisper API.
    """

    def __init__(self, model_size: str = WHISPER_MODEL_SIZE):
        self.model_size = model_size
        self._model = None  # Lazy load

    def _load_model(self):
        """Load faster-whisper model (lazy — chỉ load khi cần)."""
        if self._model is None and not USE_OPENAI_WHISPER_API:
            try:
                from faster_whisper import WhisperModel

                # Kiểm tra model đã cached chưa
                cached = _is_model_cached(self.model_size)
                est = MODEL_ESTIMATED_SIZE.get(self.model_size, "?")
                if not cached:
                    logger.warning(
                        f"⚠️ Model '{self.model_size}' ({est}) chưa được download! "
                        f"Lần đầu sẽ tải {'~' + est if est != '?' else ''} từ HuggingFace..."
                    )
                    logger.warning("⏳ Quá trình này có thể mất 5-30 phút tùy tốc độ mạng.")
                else:
                    logger.info(f"✅ Model '{self.model_size}' ({est}) đã có sẵn trong cache.")

                logger.info(f"📥 Đang load faster-whisper model: {self.model_size} (CPU, int8)...")
                self._model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8",
                    download_root=None,  # Mặc định HuggingFace cache
                )
                logger.info(f"✅ faster-whisper model '{self.model_size}' loaded.")
            except Exception as e:
                logger.error(f"❌ Lỗi load faster-whisper ({self.model_size}): {e}")
                # Fallback: thử model nhỏ hơn
                if self.model_size != "tiny":
                    logger.warning("⚠️ Fallback sang model 'tiny'...")
                    try:
                        self.model_size = "tiny"
                        self._model = WhisperModel("tiny", device="cpu", compute_type="int8")
                        logger.info("✅ Fallback thành công (tiny).")
                        return
                    except Exception as e2:
                        logger.error(f"❌ Fallback cũng thất bại: {e2}")
                raise

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> list[dict]:
        """
        Nhận diện giọng nói từ file audio.
        Args:
            audio_path: Đường dẫn file .wav
            language: Mã ngôn ngữ (ví dụ: 'zh', 'en'). None = tự động phát hiện.
        Returns:
            List[dict]: [{"start": float, "end": float, "text": str}, ...]
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"File audio không tồn tại: {audio_path}")

        if USE_OPENAI_WHISPER_API:
            return self._transcribe_api(audio_path, language)
        else:
            return self._transcribe_local(audio_path, language)

    def _transcribe_local(self, audio_path: str, language: Optional[str] = None) -> list[dict]:
        """Transcribe bằng faster-whisper local."""
        self._load_model()
        segments = []

        try:
            # Thử với VAD filter trước
            vad_params = dict(min_silence_duration_ms=2000, threshold=0.3, min_speech_duration_ms=250)
            result = self._model.transcribe(
                audio_path,
                language=language,
                beam_size=5,
                vad_filter=True,
                vad_parameters=vad_params,
            )

            segments_gen, info = (result if isinstance(result, tuple) else (result.segments, result))
            lang = info.language if hasattr(info, 'language') else result.language
            lang_prob = info.language_probability if hasattr(info, 'language_probability') else result.language_probability

            for seg in segments_gen:
                text = seg.text.strip()
                if text:
                    segments.append({
                        "start": round(seg.start, 3),
                        "end": round(seg.end, 3),
                        "text": text,
                    })

            # Nếu VAD filter xoá hết audio, thử lại không có VAD
            if not segments:
                logger.warning("VAD filter removed all audio, retrying without VAD...")
                result2 = self._model.transcribe(
                    audio_path,
                    language=language,
                    beam_size=5,
                    vad_filter=False,
                )
                segments_gen2, info2 = (result2 if isinstance(result2, tuple) else (result2.segments, result2))
                for seg in segments_gen2:
                    text = seg.text.strip()
                    if text:
                        segments.append({
                            "start": round(seg.start, 3),
                            "end": round(seg.end, 3),
                            "text": text,
                        })

            logger.info(
                f"✅ Transcribed {len(segments)} segments "
                f"(language: {lang}, probability: {lang_prob:.2f})"
            )

        except Exception as e:
            logger.error(f"❌ Lỗi transcribe local: {e}")
            raise

        return segments

    def _transcribe_api(self, audio_path: str, language: Optional[str] = None) -> list[dict]:
        """Transcribe bằng OpenAI Whisper API."""
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY chưa được cấu hình.")

        try:
            import openai
            client = openai.OpenAI(api_key=OPENAI_API_KEY)

            with open(audio_path, "rb") as f:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                    language=language,
                )

            segments = []
            for seg in response.segments:
                text = seg.text.strip()
                if text:
                    segments.append({
                        "start": round(seg.start, 3),
                        "end": round(seg.end, 3),
                        "text": text,
                    })

            logger.info(f"✅ API transcribed {len(segments)} segments.")
            return segments

        except Exception as e:
            logger.error(f"❌ Lỗi transcribe API: {e}")
            raise

    def save_segments_to_json(self, segments: list[dict], output_path: str):
        """Lưu segments ra file JSON để debug."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Saved {len(segments)} segments to {output_path}")
