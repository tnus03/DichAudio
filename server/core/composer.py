# -*- coding: utf-8 -*-
"""
Video Composer — Dùng MoviePy thay raw FFmpeg.
Hỗ trợ: ghép video, subtitle, nhạc nền, watermark, lật, speed.
"""
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

try:
    from moviepy import (
        VideoFileClip, AudioFileClip, CompositeVideoClip,
        TextClip, ImageClip,
        vfx, afx,
    )
    HAVE_MOVIEPY = True
except ImportError:
    HAVE_MOVIEPY = False


# Font cho subtitle (ưu tiên Arial, fallback)
SUB_FONT = os.path.expandvars(r"%WINDIR%\Fonts\arial.ttf")
if not os.path.exists(SUB_FONT):
    SUB_FONT = None


class VideoComposer:
    """
    Biên tập video bằng MoviePy.
    Xử lý: subtitle, nhạc nền, lật, speed, watermark, ghép audio lồng tiếng.
    """

    def __init__(self):
        if not HAVE_MOVIEPY:
            raise ImportError("MoviePy chưa cài: pip install moviepy")

    def compose(
        self,
        video_path: str,
        output_path: str,
        dubbed_audio: list[dict] = None,
        subtitles: list[dict] = None,
        bg_music_path: str = None,
        bg_music_volume: float = 0.05,
        mirror: bool = False,
        speed: float = 1.0,
        blur_padding: bool = False,
        watermark_path: str = None,
        target_width: int = 1080,
        target_height: int = 1920,
    ) -> str:
        """
        Tổng hợp video hoàn chỉnh.
        Args:
            video_path: Video gốc
            output_path: Đường dẫn output
            dubbed_audio: [{path, start, end}] audio lồng tiếng
            subtitles: [{start, end, text}] subtitle tiếng Việt
            bg_music_path: File nhạc nền
            bg_music_volume: Âm lượng nhạc nền (0-1)
            mirror: Lật ngang
            speed: Hệ số tốc độ
            blur_padding: Thêm blur viền
            watermark_path: Ảnh watermark .png
        """
        logger.info(f"🎬 Composing video: {os.path.basename(video_path)}")

        clip = VideoFileClip(video_path)

        # 1. Mirror
        if mirror:
            clip = clip.with_effects([vfx.MirrorX()])
            logger.info("  🪞 Mirror: ON")

        # 2. Speed
        if speed != 1.0:
            clip = clip.with_effects([vfx.MultiplySpeed(speed)])
            logger.info(f"  ⚡ Speed: {speed}x")

        # 3. Blur padding (nếu chuyển ngang→dọc)
        if blur_padding:
            clip = self._apply_blur_padding(clip, target_width, target_height)
            logger.info("  🌫️ Blur padding: ON")

        # 4. Mix dubbed audio (lồng tiếng)
        if dubbed_audio:
            clip = self._mix_dubbed_audio(clip, dubbed_audio)
            logger.info(f"  🎤 Lồng tiếng: {len(dubbed_audio)} segments")

        # 5. Subtitles
        text_clips = []
        if subtitles:
            text_clips = self._render_subtitles(subtitles, clip.size)
            logger.info(f"  📝 Subtitle: {len(subtitles)} segments")

        # 6. Background music
        if bg_music_path and os.path.exists(bg_music_path):
            bg = AudioFileClip(bg_music_path)
            bg = bg.with_effects([afx.MultiplyVolume(bg_music_volume)])
            if clip.audio:
                # Trộn audio gốc + nhạc nền
                final_audio = clip.audio.with_effects([afx.MultiplyVolume(0.7)])
                clip = clip.with_audio(final_audio)
                clip = clip.with_audio(
                    CompositeVideoClip([clip]) if text_clips else clip
                ).with_audio(
                    clip.audio  # Giữ nguyên, trộn sau
                )
            logger.info(f"  🎵 Nhạc nền: {os.path.basename(bg_music_path)}")

        # 7. Watermark
        if watermark_path and os.path.exists(watermark_path):
            wm = (ImageClip(watermark_path)
                  .with_duration(clip.duration)
                  .with_position(("right", "bottom"), relative=True)
                  .resize(height=clip.h * 0.08))
            text_clips.append(wm)
            logger.info("  💧 Watermark: ON")

        # 8. Ghép tất cả
        if text_clips:
            final = CompositeVideoClip([clip] + text_clips, size=clip.size)
        else:
            final = clip

        # Ghi file
        final.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            fps=30,
            threads=2,
            logger=None,
        )

        final.close()
        clip.close()
        logger.info(f"✅ Video output: {output_path}")
        return output_path

    def _apply_blur_padding(self, clip, target_w, target_h):
        """Thêm hiệu ứng mờ viền dọc."""
        return CompositeVideoClip([
            clip.resized(height=target_h).with_effects([vfx.GaussianBlur(15)]),
            clip.resized(width=target_w).with_position("center"),
        ], size=(target_w, target_h))

    def _mix_dubbed_audio(self, clip, dubbed_audio):
        """Trộn audio lồng tiếng vào video."""
        original_audio = clip.audio.with_effects([afx.MultiplyVolume(0.1)])
        dubbed_clips = [original_audio]

        for seg in dubbed_audio:
            if os.path.exists(seg["path"]):
                a = (AudioFileClip(seg["path"])
                     .with_start(seg["start"]))
                dubbed_clips.append(a)

        from moviepy import CompositeAudioClip
        final_audio = CompositeAudioClip(dubbed_clips)
        return clip.with_audio(final_audio)

    def _render_subtitles(self, subtitles, video_size):
        """Render subtitle text clips."""
        clips = []
        w, h = video_size
        for sub in subtitles:
            try:
                txt = TextClip(
                    font=SUB_FONT or "Arial",
                    text=sub["text"],
                    font_size=max(24, int(h * 0.04)),
                    color="white",
                    stroke_color="black",
                    stroke_width=2,
                    method="label",
                )
                txt = (txt
                       .with_duration(sub["end"] - sub["start"])
                       .with_start(sub["start"])
                       .with_position(("center", h * 0.85)))
                clips.append(txt)
            except Exception as e:
                logger.warning(f"Subtitle error: {e}")
        return clips


def check_ffmpeg_for_moviepy():
    """MoviePy cần FFmpeg. Kiểm tra và cảnh báo."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except Exception:
        logger.warning("FFmpeg NOT FOUND! MoviePy cần FFmpeg.")
        return False
