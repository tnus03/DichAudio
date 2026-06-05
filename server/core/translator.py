"""
Translation Module — Google Gemini 1.5 Flash API.
Dịch sát nghĩa theo ngữ cảnh, giữ nguyên timestamps gốc.
Bắt buộc trả về cấu trúc JSON.
"""
import json
import logging
import time

from server.config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# Prompt mẫu cho Gemini — ép định dạng JSON output
TRANSLATION_PROMPT_TEMPLATE = """
Bạn là một chuyên gia dịch thuật đa ngôn ngữ. Nhiệm vụ của bạn là dịch các đoạn hội thoại
sau đây từ ngôn ngữ gốc sang tiếng Việt.

## YÊU CẦU:
1. Dịch SÁT NGHĨA, trung thành với ngữ cảnh của video gốc
2. Giữ nguyên các thuật ngữ chuyên ngành, tên riêng, tiếng lóng phù hợp
3. Câu dịch phải tự nhiên, dễ hiểu trong tiếng Việt
4. TUYỆT ĐỐI giữ nguyên cấu trúc JSON: mỗi segment phải có "start", "end", "original_text", "translated_text"
5. KHÔNG thay đổi, thêm bớt timestamps (start, end)
6. KHÔNG thêm bất kỳ text nào ngoài JSON array

## INPUT (JSON Array):
{input_segments}

## OUTPUT (CHỈ trả về JSON Array, không kèm giải thích):
"""


class GeminiTranslator:
    """Dịch thuật qua Gemini 1.5 Flash API với retry mechanism."""

    def __init__(self, api_key: str = GEMINI_API_KEY):
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        """Khởi tạo Gemini client (lazy)."""
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "GEMINI_API_KEY chưa được cấu hình. "
                    "Set biến môi trường GEMINI_API_KEY trong .env"
                )
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"❌ Lỗi khởi tạo Gemini client: {e}")
                raise
        return self._client

    def translate(
        self,
        segments: list[dict],
        max_retries: int = 3,
        retry_delay: float = 2.0
    ) -> list[dict]:
        """
        Dịch danh sách segments sang tiếng Việt.
        Args:
            segments: [{"start": float, "end": float, "text": str}]
            max_retries: Số lần thử lại nếu lỗi API
            retry_delay: Giây chờ giữa các lần retry
        Returns:
            [{"start": float, "end": float, "original_text": str, "translated_text": str}]
        """
        # Chia nhỏ segments nếu quá dài (Gemini context limit ~1M tokens)
        batch_size = 50
        all_translated = []

        for i in range(0, len(segments), batch_size):
            batch = segments[i:i + batch_size]
            translated_batch = self._translate_batch(batch, max_retries, retry_delay)
            all_translated.extend(translated_batch)

        logger.info(f"✅ Translated {len(all_translated)} segments.")
        return all_translated

    def _translate_batch(
        self,
        segments: list[dict],
        max_retries: int,
        retry_delay: float
    ) -> list[dict]:
        """Dịch một batch segments."""
        client = self._get_client()

        # Format input
        input_data = []
        for seg in segments:
            input_data.append({
                "start": seg["start"],
                "end": seg["end"],
                "original_text": seg["text"],
            })

        prompt = TRANSLATION_PROMPT_TEMPLATE.format(
            input_segments=json.dumps(input_data, ensure_ascii=False, indent=2)
        )

        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config={
                        "temperature": 0.3,
                        "top_p": 0.95,
                        "response_mime_type": "application/json",
                    }
                )

                raw_text = response.text.strip()
                # Loại bỏ markdown code block nếu có
                if raw_text.startswith("```"):
                    raw_text = raw_text.strip("`").strip()
                    if raw_text.startswith("json"):
                        raw_text = raw_text[4:].strip()

                translated = json.loads(raw_text)

                if not isinstance(translated, list):
                    raise ValueError(f"Gemini trả về không phải list: {type(translated)}")

                # Validate và map lại fields
                result = []
                for item in translated:
                    result.append({
                        "start": float(item.get("start", 0)),
                        "end": float(item.get("end", 0)),
                        "original_text": item.get("original_text", ""),
                        "translated_text": item.get("translated_text", ""),
                    })

                return result

            except json.JSONDecodeError as e:
                logger.warning(
                    f"⚠️ Lỗi JSON attempt {attempt + 1}/{max_retries}: {e}"
                )
            except Exception as e:
                logger.warning(
                    f"⚠️ Lỗi Gemini API attempt {attempt + 1}/{max_retries}: {e}"
                )

            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff

        # Fallback: trả về bản dịch giữ nguyên text gốc
        logger.error(f"❌ Dịch thất bại sau {max_retries} lần thử. Fallback text gốc.")
        return [
            {
                "start": seg["start"],
                "end": seg["end"],
                "original_text": seg["text"],
                "translated_text": seg["text"],  # Giữ nguyên text gốc
            }
            for seg in segments
        ]
