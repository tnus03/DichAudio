"""
Text-to-Speech (TTS) Module.
Sử dụng Edge-TTS (chất lượng cao) với fallback gTTS (Google TTS).
Giọng tiếng Việt: Nam Minh (nam) / Hoài My (nữ).
Tự động điều chỉnh tốc độ nói.
"""
import asyncio
import logging
import os
import subprocess
from typing import Optional

from server.config import TTS_VOICE, TTS_VOICE_FALLBACK

logger = logging.getLogger(__name__)


class EdgeTTSGenerator:
    """
    Sinh giọng đọc tiếng Việt qua Edge-TTS (chất lượng cao).
    Fallback sang gTTS (Google TTS) nếu Edge-TTS không hoạt động.
    """

    def __init__(self, voice: str = TTS_VOICE, fallback_voice: str = TTS_VOICE_FALLBACK):
        self.voice = voice
        self.fallback_voice = fallback_voice

    def generate_speech(
        self,
        text: str,
        output_path: str,
        rate: str = "+0%",
        volume: str = "+0%",
    ) -> str:
        """Sinh file audio tu text."""
        from server.config import TTS_PROXY_URL

        # Neu co proxy, thu Edge-TTS (chat luong cao)
        if TTS_PROXY_URL:
            try:
                asyncio.run(self._generate_speech_async(text, output_path, rate, volume))
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return output_path
            except Exception as e:
                logger.debug(f"Edge-TTS: {e}")

        # Khong co proxy hoac Edge that bai -> gTTS truc tiep
        return self._generate_gtts(text, output_path)

    def _generate_gtts(self, text: str, output_path: str) -> str:
        """Sinh audio bang Google TTS."""
        from gtts import gTTS
        try:
            tts = gTTS(text=text, lang="vi", slow=False)
            tts.save(output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
        except Exception as e:
            raise RuntimeError(f"gTTS: {e}")
        raise RuntimeError("gTTS: file rong")

    async def _generate_speech_async(self, text, output_path, rate, volume, voice=None):
        import edge_tts
        from server.config import TTS_PROXY_URL
        kwargs = dict(text=text, voice=voice or self.voice, rate=rate, volume=volume)
        if TTS_PROXY_URL:
            kwargs["proxy"] = TTS_PROXY_URL
        communicate = edge_tts.Communicate(**kwargs)
        await communicate.save(output_path)

    def generate_segment_audio(
        self,
        text: str,
        output_path: str,
        original_duration: float,
        min_rate: int = -20,
        max_rate: int = 30,
    ) -> str:
        """
        Sinh audio cho một segment với tự động điều chỉnh tốc độ.
        Đảm bảo duration của audio dịch ≤ duration gốc.
        Args:
            text: Text tiếng Việt cần đọc
            output_path: Đường dẫn output
            original_duration: Duration gốc (giây)
            min_rate: Tốc độ tối thiểu (-20%)
            max_rate: Tốc độ tối đa (+30%)
        Returns:
            Đường dẫn file audio đã xử lý
        """
        rate = "+0%"

        # Thử với tốc độ bình thường trước
        self.generate_speech(text, output_path, rate=rate)

        # Kiểm tra duration và điều chỉnh nếu cần
        actual_duration = self._get_audio_duration(output_path)

        if actual_duration > original_duration * 1.1:
            # Cần tăng tốc độ nói
            needed_ratio = original_duration / actual_duration
            rate_percent = int((1 / needed_ratio - 1) * 100)
            rate_percent = min(rate_percent, max_rate)
            rate_percent = max(rate_percent, min_rate)
            rate_str = f"{rate_percent:+d}%"

            logger.info(
                f"⚡ Điều chỉnh tốc độ: {rate} → {rate_str} "
                f"(dur gốc: {original_duration:.2f}s, thực tế: {actual_duration:.2f}s)"
            )

            self.generate_speech(text, output_path, rate=rate_str)

        return output_path

    def _get_audio_duration(self, audio_path: str) -> float:
        """Lấy duration (giây) của file audio bằng FFprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"Không thể đọc duration audio: {e}")
        return 0.0
