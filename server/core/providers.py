# -*- coding: utf-8 -*-
"""
Pluggable Translation Providers.
Mỗi provider implement cùng interface: translate(segments) -> list[dict]
Hiện tại: Gemini, OpenAI, DeepSeek
"""
import json, logging, time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseTranslator(ABC):
    @abstractmethod
    def translate(self, segments: list[dict], max_retries: int = 3, target_language: str = "Vietnamese") -> list[dict]:
        ...


PROMPT_TEMPLATE = """
Translate the following dialogue segments to {target_language}.
Rules:
- Keep exact start/end timestamps
- Natural {target_language}, context-aware
- Keep proper nouns, technical terms
- Return ONLY valid JSON array

INPUT:
{input_segments}

OUTPUT (JSON array only):
"""


class GeminiTranslator(BaseTranslator):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None
        self._models = ["gemini-2.0-flash", "gemini-1.5-flash"]

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def translate(self, segments: list[dict], max_retries: int = 3, target_language: str = "Vietnamese") -> list[dict]:
        client = self._get_client()
        input_data = [{"start": s["start"], "end": s["end"], "original_text": s["text"]} for s in segments]
        prompt = PROMPT_TEMPLATE.format(target_language=target_language, input_segments=json.dumps(input_data, ensure_ascii=False))

        for model in self._models:
            for attempt in range(max_retries):
                try:
                    resp = client.models.generate_content(
                        model=model, contents=prompt,
                        config={"temperature": 0.3, "response_mime_type": "application/json"},
                    )
                    raw = resp.text.strip().removeprefix("```json").removesuffix("```").strip()
                    return [{"start": float(r["start"]), "end": float(r["end"]),
                             "original_text": r["original_text"], "translated_text": r["translated_text"]}
                            for r in json.loads(raw)]
                except Exception as e:
                    err_str = str(e)
                    logger.warning(f"Gemini {model} attempt {attempt+1}: {str(err_str)[:100]}")
                    if "RESOURCE_EXHAUSTED" in err_str:
                        if "limit: 0" in err_str or "FreeTier" in err_str:
                            logger.warning(f"  Daily quota for {model}, trying next model...")
                            break
                        logger.info(f"  Rate limit, waiting {15*(attempt+1)}s...")
                        time.sleep(15 * (attempt + 1))
                    elif "not found" in err_str.lower() or "404" in err_str:
                        logger.warning(f"  Model {model} not available, trying next...")
                        break
                    else:
                        time.sleep(2 ** attempt)

        logger.warning("All Gemini models failed, keeping original text.")
        return [{"start": s["start"], "end": s["end"], "original_text": s["text"], "translated_text": s["text"]}
                for s in segments]


class OpenAITranslator(BaseTranslator):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: str = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    def translate(self, segments: list[dict], max_retries: int = 3, target_language: str = "Vietnamese") -> list[dict]:
        import openai
        client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        input_data = [{"start": s["start"], "end": s["end"], "original_text": s["text"]} for s in segments]
        prompt = PROMPT_TEMPLATE.format(target_language=target_language, input_segments=json.dumps(input_data, ensure_ascii=False))

        for attempt in range(max_retries):
            try:
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3, response_format={"type": "json_object"},
                )
                raw = resp.choices[0].message.content
                data = json.loads(raw)
                results = data.get("segments", data.get("translations", data if isinstance(data, list) else []))
                return [{"start": float(r["start"]), "end": float(r["end"]),
                         "original_text": r["original_text"], "translated_text": r["translated_text"]}
                        for r in results]
            except Exception as e:
                logger.warning(f"OpenAI attempt {attempt+1} fail: {e}")
                time.sleep(2 ** attempt)
        return [{"start": s["start"], "end": s["end"], "original_text": s["text"], "translated_text": s["text"]}
                for s in segments]


class DeepSeekTranslator(OpenAITranslator):
    """DeepSeek tương thích OpenAI API format."""
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        super().__init__(api_key=api_key, model=model, base_url="https://api.deepseek.com")


PROVIDER_MAP = {
    "gemini": GeminiTranslator,
    "openai": OpenAITranslator,
    "deepseek": DeepSeekTranslator,
}


class AutoFallbackTranslator(BaseTranslator):
    """
    Tự động thử lần lượt các provider cho đến khi thành công.
    Thứ tự: gemini → openai → deepseek → fallback text gốc.
    """

    def __init__(self):
        from server.config import GEMINI_API_KEY, OPENAI_API_KEY
        self._providers = []

        if GEMINI_API_KEY:
            self._providers.append(GeminiTranslator(api_key=GEMINI_API_KEY))
        if OPENAI_API_KEY:
            self._providers.append(OpenAITranslator(api_key=OPENAI_API_KEY))

        # DeepSeek cần key riêng
        deepseek_key = ""
        import os
        deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
        if deepseek_key:
            self._providers.append(DeepSeekTranslator(api_key=deepseek_key))

    def translate(self, segments: list[dict], max_retries: int = 2, target_language: str = "Vietnamese") -> list[dict]:
        for provider in self._providers:
            try:
                logger.info(f"AutoFallback: trying {type(provider).__name__}...")
                result = provider.translate(segments, max_retries=max_retries, target_language=target_language)
                # Check if result is actual translation or fallback (original text kept)
                if result and result[0].get("translated_text") != result[0].get("original_text"):
                    logger.info(f"AutoFallback: {type(provider).__name__} succeeded!")
                    return result
                # If text unchanged and more providers available, try next
                logger.warning(f"AutoFallback: {type(provider).__name__} returned unchanged text, trying next...")
            except Exception as e:
                logger.warning(f"AutoFallback: {type(provider).__name__} failed: {str(e)[:100]}, trying next...")
                continue

        # All providers failed: return original text
        logger.warning("AutoFallback: all providers exhausted, keeping original text.")
        return [{"start": s["start"], "end": s["end"],
                 "original_text": s["text"], "translated_text": s["text"]}
                for s in segments]


def get_translator(provider: str = "gemini", api_key: str = "", **kwargs) -> BaseTranslator:
    """Factory: tạo translator theo tên provider."""
    if provider.lower() == "auto":
        return AutoFallbackTranslator()

    cls = PROVIDER_MAP.get(provider.lower())
    if not cls:
        raise ValueError(f"Unknown provider: {provider}. Options: {list(PROVIDER_MAP.keys()) + ['auto']}")
    # Ưu tiên api_key từ kwargs, fallback config
    if not api_key:
        from server.config import GEMINI_API_KEY, OPENAI_API_KEY
        api_key = {"gemini": GEMINI_API_KEY, "openai": OPENAI_API_KEY, "deepseek": kwargs.get("deepseek_key", "")}.get(provider, "")
    return cls(api_key=api_key, **kwargs)
