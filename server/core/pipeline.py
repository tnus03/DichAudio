"""
Pipeline Orchestrator — Điều phối toàn bộ quy trình xử lý video.
Kết nối: Download → STT → Translate → TTS → Video Editing → Upload.
Mỗi bước đều có try-except để không crash toàn bộ pipeline.
"""
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from server.config import MEDIA_DIR
from server.core.stt import WhisperSTT
from server.core.providers import get_translator
from server.core.tts import EdgeTTSGenerator
from server.core.video_editor import VideoEditor

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    Điều phối toàn bộ pipeline xử lý video.
    Mỗi bước được bọc trong try-except, nếu lỗi → set status FAILED + log.

    Status flow:
    PENDING → DOWNLOADING → EXTRACTING_AUDIO → TRANSCRIBING → TRANSLATING
    → GENERATING_VOICE → EDITING_AND_MERGING → UPLOADING → COMPLETED
    """

    def __init__(self, translation_provider: str = "auto"):
        self.stt = WhisperSTT()
        self.translator = get_translator(provider=translation_provider)
        self.tts = EdgeTTSGenerator()
        self.editor = VideoEditor()
        self._composer = None  # Lazy load MoviePy composer
        self._status_callback = None

    @property
    def composer(self):
        """Lazy load composer — tránh lỗi nếu không có MoviePy."""
        if self._composer is None:
            try:
                from server.core.composer import VideoComposer
                self._composer = VideoComposer()
            except ImportError:
                logger.warning("MoviePy chưa cài đặt, bỏ qua composer.")
                self._composer = None
        return self._composer

    def set_status_callback(self, callback):
        """
        Set callback function để cập nhật status trong database.
        Callback signature: func(task_id: int, status: str, **extra)
        """
        self._status_callback = callback

    def _update_status(self, task_id: int, status: str, **extra):
        """Cập nhật trạng thái task qua callback."""
        if self._status_callback:
            try:
                self._status_callback(task_id, status, **extra)
            except Exception as e:
                logger.error(f"Lỗi update status: {e}")
        logger.info(f"[Task {task_id}] Status: {status}")


    def process_video(
        self,
        task_id: int,
        source_url: str,
        options: Optional[dict] = None,
    ) -> str:
        """
        Xử lý toàn bộ pipeline cho một video.
        Args:
            task_id: ID task trong database
            source_url: URL video cần xử lý
            options: Dict chứa các tùy chọn chỉnh sửa
        Returns:
            URL video đã dịch (Cloudinary) hoặc chuỗi rỗng nếu thất bại
        """
        opts = options or {}
        provider = opts.get("translation_provider", "gemini")
        self.translator = get_translator(provider=provider)
        task_dir = MEDIA_DIR / f"task_{task_id}"
        task_dir.mkdir(parents=True, exist_ok=True)

        video_path = None
        translated_url = ""

        try:
            # Check if local file upload
            is_local = source_url.startswith("upload://") or os.path.isfile(source_url)
            if is_local:
                if source_url.startswith("upload://"):
                    local_path = str(MEDIA_DIR / "uploads" / source_url[9:])
                else:
                    local_path = source_url
                import shutil
                video_path = str(task_dir / f"input{Path(local_path).suffix or '.mp4'}")
                if not os.path.exists(local_path):
                    raise FileNotFoundError(f"File khong ton tai: {local_path}")
                shutil.copy2(local_path, video_path)
                logger.info(f"File local: {video_path}")
                self._update_status(task_id, "DOWNLOADING")
                self._update_status(task_id, "EXTRACTING_AUDIO")
            else:
                self._update_status(task_id, "DOWNLOADING")
                video_path = self._download_video(source_url, task_dir)
            if not video_path:
                raise RuntimeError("Tai video that bai.")

            # === BƯỚC 2: EXTRACT AUDIO ===
            self._update_status(task_id, "EXTRACTING_AUDIO")
            audio_path = str(task_dir / "audio.wav")
            self.editor.extract_audio(video_path, audio_path)

            # === BƯỚC 3: STT (Whisper) ===
            self._update_status(task_id, "TRANSCRIBING")
            segments = self.stt.transcribe(audio_path)
            if not segments:
                raise RuntimeError("Không nhận diện được giọng nói.")

            # Lưu segments gốc để debug
            self.stt.save_segments_to_json(
                segments, str(task_dir / "segments_original.json")
            )

            # === BƯỚC 4: DỊCH (Gemini) ===
            self._update_status(task_id, "TRANSLATING")
            translated_segments = self.translator.translate(segments)
            with open(
                task_dir / "segments_translated.json", "w", encoding="utf-8"
            ) as f:
                json.dump(translated_segments, f, ensure_ascii=False, indent=2)

            # === BƯỚC 5: TTS (Edge-TTS) ===
            self._update_status(task_id, "GENERATING_VOICE")
            dubbed_audio_paths = self._generate_voices(
                translated_segments, task_dir
            )

            # Chuẩn bị subtitle data từ bản dịch
            opts["subtitles"] = [
                {"start": s["start"], "end": s["end"], "text": s.get("translated_text", "")}
                for s in translated_segments if s.get("translated_text", "").strip()
            ]

            # === BƯỚC 6: EDIT & MERGE VIDEO ===
            self._update_status(task_id, "EDITING_AND_MERGING")
            output_path = self._edit_video(
                video_path, dubbed_audio_paths, task_dir, opts
            )

            # === BƯỚC 7: UPLOAD ===
            self._update_status(task_id, "UPLOADING")
            translated_url = self._upload_to_cloudinary(output_path)
            if not translated_url:
                # Upload thất bại vẫn giữ file local
                logger.warning("Upload Cloudinary thất bại, giữ file local.")
                translated_url = ""

            # === HOÀN THÀNH ===
            self._update_status(
                task_id, "COMPLETED", translated_url=translated_url
            )
            logger.info(f"✅ Task {task_id} hoàn thành!")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Task {task_id} thất bại: {error_msg}")
            self._update_status(task_id, "FAILED", error_message=error_msg)

        finally:
            # Dọn dẹp: xóa thư mục tạm (giữ video gốc nếu cần debug)
            try:
                shutil.rmtree(task_dir, ignore_errors=True)
            except Exception:
                pass

        return translated_url

    def _detect_platform(self, url: str) -> str:
        url_lower = url.lower()
        if "tiktok.com" in url_lower: return "tiktok"
        if "douyin.com" in url_lower or "iesdouyin.com" in url_lower: return "douyin"
        if "youtube.com" in url_lower or "youtu.be" in url_lower: return "youtube"
        if "facebook.com" in url_lower or "fb.com" in url_lower or "fb.watch" in url_lower: return "facebook"
        if "instagram.com" in url_lower: return "instagram"
        if "twitter.com" in url_lower or "x.com" in url_lower: return "twitter"
        return "unknown"

    def _validate_video_url(self, url: str) -> Optional[str]:
        platform = self._detect_platform(url)
        url_lower = url.lower()
        if platform == "youtube" and "list=" in url_lower and "watch?v=" not in url_lower:
            return "URL la playlist YouTube. Hay dung link video don: https://www.youtube.com/watch?v=..."
        if platform == "facebook" and not any(x in url_lower for x in ["/videos/", "/watch", "/reel/"]):
            return "URL Facebook khong hop le. Hay dung link: https://www.facebook.com/watch/?v=..."
        if platform == "unknown":
            return "Khong nhan dien duoc nen tang. Ho tro: TikTok, Douyin, YouTube, Facebook, Instagram."
        return None

    def _is_douyin_user_url(self, url: str) -> bool:
        return "douyin.com" in url.lower() and "/user/" in url.lower()

    def _resolve_douyin_user_url(self, url: str) -> Optional[str]:
        """Thu lay video moi nhat tu Douyin user page."""
        import requests, re
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            r = requests.get(url, headers=headers, timeout=10)
            ids = re.findall(r'/video/(\d{19,})', r.text)
            unique_ids = list(dict.fromkeys(ids))
            if unique_ids:
                video_url = f"https://www.douyin.com/video/{unique_ids[0]}"
                logger.info(f"Douyin user page: tim thay video {unique_ids[0]}")
                return video_url
            logger.warning("Khong tim thay video ID trong Douyin user page (trang can JavaScript)")
        except Exception as e:
            logger.warning(f"Loi phan tich Douyin user page: {e}")
        return None

    def _download_video(self, url: str, output_dir: Path) -> Optional[str]:
        validation_error = self._validate_video_url(url)
        if validation_error:
            logger.error(f"URL loi: {validation_error}")
            return None

        # Strip tracking query params (giu nguyen video ID)
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        clean_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        if clean_url and clean_url != url:
            logger.info(f"URL sach: {clean_url[:60]}...")
            url = clean_url

        platform = self._detect_platform(url)
        is_douyin_user = self._is_douyin_user_url(url)

        # Douyin user URL: thu phan tich de lay video cu the
        if is_douyin_user:
            resolved = self._resolve_douyin_user_url(url)
            if resolved:
                logger.info(f"Chuyen Douyin user URL -> video URL: {resolved}")
                url = resolved
                is_douyin_user = False
            else:
                logger.error("Khong the trich xuat video tu Douyin user page. Hay dung link: https://www.douyin.com/video/...")
                return None

        output_template = str(output_dir / "%(title).100s.%(ext)s")

        base_cmd = ["yt-dlp", "--no-warnings", "--print", "after_move:filepath"]

        # TikTok can't use --output (causes extract failure)
        if platform == "tiktok":
            base_cmd += ["-P", str(output_dir)]
        else:
            base_cmd += ["--output", output_template]

        extractor_args = {
            "tiktok": "tiktok:app_id=1233;api_hostname=api16-normal-c-useast1a-tiktok.com",
            "douyin": "douyin:app_id=1233",
            "facebook": "facebook:user_agent=facebookexternalhit/1.1",
            "youtube": "youtube:player_client=android,web;skip=webpage",
        }
        if platform in extractor_args:
            base_cmd += ["--extractor-args", extractor_args[platform]]

        if platform == "facebook":
            base_cmd += ["--format", "best[height<=720]"]
        elif platform == "tiktok":
            base_cmd += ["--format", "best"]
        else:
            base_cmd += ["--format", "bestvideo[height<=720]+bestaudio/best[height<=720]"]

        cookie_from_browser = None
        for b in ["firefox", "chrome", "edge", "brave"]:
            try:
                r = subprocess.run(["yt-dlp", "--cookies-from-browser", b, "--cookies", "-", "--version"], capture_output=True, encoding="utf-8", errors="replace", timeout=10)
                if r.returncode == 0:
                    base_cmd += ["--cookies-from-browser", b]
                    logger.info(f"Cookies tu {b}")
                    cookie_from_browser = b
                    break
            except Exception: continue

        # Thu cookies file (u tien cho platform kho tinh nhu Douyin)
        cookie_file = None
        for p in [r"C:\Temp\www.douyin.com_cookies.txt"]:
            if os.path.exists(p):
                cookie_file = p
                break
        if cookie_file:
            base_cmd = [c for i, c in enumerate(base_cmd) if not (c == "--cookies-from-browser" or (i > 0 and base_cmd[i-1] == "--cookies-from-browser"))]
            base_cmd += ["--cookies", cookie_file]
            logger.info(f"Dung cookies file: {cookie_file}")

        # Chien luoc tai (single video)
        strategies = [("default", base_cmd + ["--no-playlist"])]
        if "--cookies-from-browser" in str(base_cmd):
            no_cookie = [c for i, c in enumerate(base_cmd) if not (c == "--cookies-from-browser" or (i > 0 and base_cmd[i-1] == "--cookies-from-browser"))]
            strategies.append(("no-cookies", no_cookie + ["--no-playlist"]))
        # Fallback format cho TikTok (dung best thay vi bestvideo+bestaudio)
        if platform in ("tiktok",):
            fallback_fmt = [c for i, c in enumerate(base_cmd) if not (c == "--format" or (i > 0 and base_cmd[i-1] == "--format"))]
            fallback_fmt += ["--format", "best[height<=720]"]
            strategies.append(("best-fallback", fallback_fmt))
        if platform in ("facebook", "douyin"):
            fallback = [c for i, c in enumerate(base_cmd) if not (
                c == "--cookies-from-browser" or c == "--format" or c == "--cookies"
                or (i > 0 and base_cmd[i-1] == "--cookies-from-browser")
                or (i > 0 and base_cmd[i-1] == "--cookies")
            )]
            fallback += ["--format", "worst[height<=480]"]
            strategies.append(("low-res", fallback))

        for name, cmd in strategies:
            logger.info(f"[{name}] Tai {platform}: {url[:60]}...")
            try:
                result = subprocess.run(cmd + [url], capture_output=True, encoding="utf-8", errors="replace", timeout=300)
            except subprocess.TimeoutExpired:
                logger.error(f"[{name}] Timeout"); continue
            except Exception as e:
                logger.error(f"[{name}] Loi: {e}"); continue

            if result.returncode == 0:
                for line in reversed(result.stdout.strip().split("\n")):
                    line = line.strip()
                    if line and os.path.exists(line):
                        logger.info(f"Da tai: {line}"); return line
                for f in output_dir.iterdir():
                    if f.suffix in (".mp4", ".webm", ".mkv"):
                        return str(f)
            else:
                stderr_raw = result.stderr or ""
                logger.warning(f"[{name}] yt-dlp: {stderr_raw.strip()[:200]}")

        # Neu yt-dlp khong tai duoc, thu Playwright (cho TikTok, Douyin)
        if platform in ("tiktok", "douyin"):
            logger.info(f"yt-dlp that bai, thu Playwright cho {platform}...")
            try:
                import asyncio
                from server.utils.douyin_dl import PlaywrightDownloader
                dl = PlaywrightDownloader()
                pw_path = str(output_dir / "pw_video.mp4")
                # Lay URL truoc, sau do download (tranh goi Playwright 2 lan)
                pw_video_url = asyncio.run(dl.get_video_url(url))
                if pw_video_url:
                    pw_result = asyncio.run(dl.download_video(url, pw_path, video_url=pw_video_url))
                    if pw_result and os.path.exists(pw_result):
                        logger.info(f"Playwright tai Douyin thanh cong: {pw_result}")
                        return pw_result
            except RuntimeError as e:
                if "cannot be called from a running event loop" in str(e):
                    logger.warning("Playwright bo qua (async context)")
                else:
                    logger.warning(f"Playwright Douyin: {e}")
            except Exception as e:
                logger.warning(f"Playwright Douyin: {type(e).__name__}: {e}")

        logger.error(f"Khong the tai video: {url[:60]}...")

        platform = self._detect_platform(url)
        if platform in ("tiktok", "douyin"):
            logger.error(f"{platform}: yt-dlp extractor dang bi loi (can cap nhat hoac dung Playwright).")
            logger.error("Cach khac: Tai video thu cong va upload qua POST /api/v1/upload")
        elif platform == "facebook":
            logger.error("Facebook: can cookies dang nhap. Thu lai sau khi dang nhap Facebook trong Chrome.")
        return None

    def _generate_voices(
        self,
        translated_segments: list[dict],
        output_dir: Path,
    ) -> list[dict]:
        """
        Sinh file audio cho từng segment.
        Trả về: [{"path": str, "start": float, "end": float}, ...]
        """
        dubbed = []
        audio_dir = output_dir / "tts_segments"
        audio_dir.mkdir(exist_ok=True)

        for idx, seg in enumerate(translated_segments):
            text = seg.get("translated_text", "").strip()
            if not text:
                continue

            start = seg["start"]
            end = seg["end"]
            original_duration = end - start

            output_path = str(audio_dir / f"seg_{idx:04d}.mp3")

            try:
                self.tts.generate_segment_audio(
                    text=text,
                    output_path=output_path,
                    original_duration=original_duration,
                )
                dubbed.append({
                    "path": output_path,
                    "start": start,
                    "end": end,
                })
            except Exception as e:
                logger.warning(
                    f"⚠️ Lỗi TTS segment {idx}: {e}. Bỏ qua segment này."
                )
                continue

        logger.info(f"✅ Đã sinh {len(dubbed)}/{len(translated_segments)} segments TTS.")
        return dubbed

    def _edit_video(
        self,
        input_video: str,
        dubbed_audio: list[dict],
        output_dir: Path,
        options: dict,
    ) -> str:
        """
        Áp dụng các chỉnh sửa lên video.
        Nếu có composer (MoviePy) thì dùng để render subtitle + nhạc nền.
        """
        current_input = input_video
        temp_files = []

        try:
            # 1. Color adjustments (brightness, contrast, saturation)
            bri = float(options.get("brightness", 0.0))
            con = float(options.get("contrast", 1.0))
            sat = float(options.get("saturation", 1.0))
            if bri != 0.0 or con != 1.0 or sat != 1.0:
                try:
                    color_out = str(output_dir / "color_adjusted.mp4")
                    current_input = self.editor.adjust_colors(current_input, color_out, bri, con, sat)
                    temp_files.append(current_input)
                except Exception as e:
                    logger.warning(f"Color adjust failed: {e}, skipping.")

            # 2. Rotate
            rotate = int(options.get("rotate", 0))
            if rotate in (90, 180, 270, -90):
                try:
                    rot_out = str(output_dir / "rotated.mp4")
                    current_input = self.editor.rotate_video(current_input, rot_out, rotate)
                    temp_files.append(current_input)
                except Exception as e:
                    logger.warning(f"Rotate failed: {e}, skipping.")

            # 3. Crop
            crop_t = int(options.get("crop_top", 0))
            crop_b = int(options.get("crop_bottom", 0))
            crop_l = int(options.get("crop_left", 0))
            crop_r = int(options.get("crop_right", 0))
            if any([crop_t, crop_b, crop_l, crop_r]):
                try:
                    crop_out = str(output_dir / "cropped.mp4")
                    current_input = self.editor.crop_video(current_input, crop_out, crop_t, crop_b, crop_l, crop_r)
                    temp_files.append(current_input)
                except Exception as e:
                    logger.warning(f"Crop failed: {e}, skipping.")

            # 4. Mirror
            if options.get("mirror", False):
                try:
                    mirror_out = str(output_dir / "mirrored.mp4")
                    current_input = self.editor.mirror_video(current_input, mirror_out)
                    temp_files.append(current_input)
                except Exception as e:
                    logger.warning(f"Mirror failed: {e}, skipping.")

            # 5. Change speed
            speed = float(options.get("speed", 1.0))
            if speed != 1.0:
                try:
                    speed_out = str(output_dir / f"speed_{speed}x.mp4")
                    current_input = self.editor.change_speed(current_input, speed_out, speed)
                    temp_files.append(current_input)
                except Exception as e:
                    logger.warning(f"Speed change failed: {e}, skipping.")

            # 6. Mix audio (long tieng)
            if dubbed_audio:
                try:
                    mix_out = str(output_dir / "mixed.mp4")
                    current_input = self.editor.mix_audio(current_input, dubbed_audio, mix_out)
                    temp_files.append(current_input)
                except Exception as e:
                    logger.warning(f"Audio mix failed: {e}, skipping.")

            # 7. Blur padding
            if options.get("blur_padding", False):
                try:
                    blur_out = str(output_dir / "blurred.mp4")
                    current_input = self.editor.blur_padding(current_input, blur_out)
                    temp_files.append(current_input)
                except Exception as e:
                    logger.warning(f"Blur padding failed: {e}, skipping.")

            # 8. Watermark
            watermark_url = options.get("watermark_url", "")
            if watermark_url and os.path.exists(watermark_url):
                try:
                    wm_out = str(output_dir / "watermarked.mp4")
                    current_input = self.editor.add_watermark(current_input, wm_out, watermark_url)
                    temp_files.append(current_input)
                except Exception as e:
                    logger.warning(f"Watermark failed: {e}, skipping.")

            final_output = str(output_dir / "final.mp4")
            if current_input != final_output:
                shutil.copy2(current_input, final_output)

            # 9. Subtitles (dung FFmpeg drawtext)
            sub_data = options.get("subtitles")
            if isinstance(sub_data, list) and len(sub_data) > 0:
                try:
                    sub_out = str(output_dir / "subtitled.mp4")
                    final_output = self.editor.burn_subtitles(
                        final_output, sub_out, sub_data,
                        font_size=int(options.get("subtitle_font_size", 24)),
                    )
                except Exception as e:
                    logger.warning(f"Subtitles failed: {e}, skipping.")

            # 10. Background music (MoviePy)
            bg_music = options.get("bg_music")
            if self.composer and bg_music and os.path.exists(bg_music):
                try:
                    logger.info("Adding background music...")
                    bg_out = str(output_dir / "with_bgmusic.mp4")
                    self.composer.compose(
                        video_path=final_output, output_path=bg_out,
                        bg_music_path=bg_music,
                        bg_music_volume=float(options.get("bg_music_volume", 0.05)),
                    )
                    final_output = bg_out
                except Exception as e:
                    logger.warning(f"BG music failed: {e}, skipping.")

            return final_output

        except Exception as e:
            logger.error(f"Lỗi edit video: {e}")
            raise
        finally:
            # Dọn file tạm (giữ final output)
            for f in temp_files:
                try:
                    if os.path.exists(f) and f != final_output:
                        os.remove(f)
                except Exception:
                    pass

    def _upload_to_cloudinary(self, video_path: str) -> str:
        """
        Upload video lên Cloudinary.
        Returns:
            URL video trên Cloudinary hoặc chuỗi rỗng nếu lỗi
        """
        from server.config import (
            CLOUDINARY_API_KEY,
            CLOUDINARY_API_SECRET,
            CLOUDINARY_CLOUD_NAME,
        )
        if not CLOUDINARY_CLOUD_NAME:
            logger.warning("Cloudinary chưa cấu hình, bỏ qua upload.")
            return ""

        try:
            import cloudinary
            import cloudinary.uploader

            cloudinary.config(
                cloud_name=CLOUDINARY_CLOUD_NAME,
                api_key=CLOUDINARY_API_KEY,
                api_secret=CLOUDINARY_API_SECRET,
                secure=True,
            )

            result = cloudinary.uploader.upload(
                video_path,
                resource_type="video",
                folder="dichaudio",
                eager=[
                    {"width": 720, "crop": "scale"},
                ],
                eager_async=True,
            )
            url = result.get("secure_url", "")
            logger.info(f"☁️ Uploaded: {url}")
            return url

        except Exception as e:
            logger.error(f"Lỗi upload Cloudinary: {e}")
            return ""
