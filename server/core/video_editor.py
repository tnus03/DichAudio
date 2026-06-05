"""
Video Editor Module — Xử lý video qua FFmpeg.
Các chức năng: lật hình, tăng tốc, blur padding, chèn watermark, mix audio.
"""
import logging
import os
import subprocess

from server.config import MEDIA_DIR

logger = logging.getLogger(__name__)


class VideoEditor:
    """
    Chỉnh sửa video bằng FFmpeg commands.
    Hỗ trợ các thao tác lách bản quyền và tùy biến theo yêu cầu.
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg = ffmpeg_path
        self.ffprobe = ffprobe_path
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        """Kiểm tra FFmpeg đã được cài đặt."""
        try:
            subprocess.run(
                [self.ffmpeg, "-version"],
                capture_output=True, timeout=10
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            raise RuntimeError(
                "FFmpeg không tìm thấy. Cài đặt FFmpeg và thêm vào PATH."
            )

    def extract_audio(self, video_path: str, output_path: str) -> str:
        """
        Tách âm thanh từ video thành file .wav (16kHz, mono).
        Args:
            video_path: Đường dẫn video gốc
            output_path: Đường dẫn file .wav output
        Returns:
            Đường dẫn file audio đã tách
        """
        cmd = [
            self.ffmpeg, "-y",
            "-i", video_path,
            "-vn",                    # Bỏ video
            "-acodec", "pcm_s16le",  # PCM 16-bit
            "-ar", "16000",           # Sample rate 16kHz
            "-ac", "1",               # Mono
            output_path,
        ]
        self._run_cmd(cmd, "Extract audio")
        return output_path

    def mirror_video(self, input_path: str, output_path: str) -> str:
        """
        Lật ngang khung hình (horizontal flip).
        Dùng filter hflip của FFmpeg.
        """
        cmd = [
            self.ffmpeg, "-y",
            "-i", input_path,
            "-vf", "hflip",
            "-c:a", "copy",
            output_path,
        ]
        self._run_cmd(cmd, "Mirror video")
        return output_path

    def change_speed(self, input_path: str, output_path: str, speed: float = 1.05) -> str:
        """
        Thay đổi tốc độ video (cả hình ảnh và âm thanh).
        Dùng setpts (video) + atempo (audio).
        Args:
            input_path: Đường dẫn input
            output_path: Đường dẫn output
            speed: Hệ số tốc độ (1.05, 1.1, v.v.)
        """
        # atempo chỉ hỗ trợ 0.5-2.0, cần chuỗi nếu speed > 2
        atempo_filter = self._build_atempo(speed)

        cmd = [
            self.ffmpeg, "-y",
            "-i", input_path,
            "-filter_complex",
            f"[0:v]setpts={1/speed}*PTS[v];[0:a]{atempo_filter}[a]",
            "-map", "[v]",
            "-map", "[a]",
            output_path,
        ]
        self._run_cmd(cmd, f"Change speed {speed}x")
        return output_path

    def _build_atempo(self, speed: float) -> str:
        """Xây dựng chuỗi atempo filter (hỗ trợ speed > 2)."""
        if speed <= 2.0:
            return f"atempo={speed}"
        filters = []
        remaining = speed
        while remaining > 2.0:
            filters.append("atempo=2.0")
            remaining /= 2.0
        filters.append(f"atempo={remaining}")
        return ",".join(filters)

    def blur_padding(self, input_path: str, output_path: str, target_width: int = 1080, target_height: int = 1920) -> str:
        """
        Thêm hiệu ứng mờ viền (blur padding) khi chuyển tỷ lệ.
        Video gốc được đặt ở giữa, phần còn lại fill với background mờ.
        """
        cmd = [
            self.ffmpeg, "-y",
            "-i", input_path,
            "-vf",
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black@0,"
            f"gblur=sigma=10",
            "-c:a", "copy",
            output_path,
        ]
        self._run_cmd(cmd, "Blur padding")
        return output_path

    def add_watermark(
        self,
        input_path: str,
        output_path: str,
        watermark_path: str,
        position: str = "bottom_right",
        scale: float = 0.1,
    ) -> str:
        """
        Chèn watermark (logo .png) vào góc video.
        Args:
            input_path: Video input
            output_path: Video output
            watermark_path: Đường dẫn ảnh .png
            position: Vị trí (bottom_right, bottom_left, top_right, top_left)
            scale: Tỷ lệ watermark so với video (0.0-1.0)
        """
        pos_map = {
            "bottom_right": "(W-w-10):(H-h-10)",
            "bottom_left": "10:(H-h-10)",
            "top_right": "(W-w-10):10",
            "top_left": "10:10",
        }
        overlay_pos = pos_map.get(position, pos_map["bottom_right"])

        cmd = [
            self.ffmpeg, "-y",
            "-i", input_path,
            "-i", watermark_path,
            "-filter_complex",
            f"[1:v]scale=iw*{scale}:-1[wm];"
            f"[0:v][wm]overlay={overlay_pos}",
            "-c:a", "copy",
            output_path,
        ]
        self._run_cmd(cmd, "Add watermark")
        return output_path

    def mix_audio(
        self,
        video_path: str,
        dubbed_audio_paths: list[dict],
        output_path: str,
        original_volume: float = 0.1,
    ) -> str:
        """
        Mix audio: hạ âm gốc + chèn lồng tiếng Việt vào đúng timestamps.
        Args:
            video_path: Video gốc (chứa audio gốc)
            dubbed_audio_paths: List[{"path": str, "start": float, "end": float}]
            output_path: Video output
            original_volume: Âm lượng gốc giữ lại (0.0-1.0)
        """

        # Bước 1: Hạ âm lượng audio gốc
        temp_low = os.path.join(MEDIA_DIR, f"temp_low_{os.getpid()}.wav")
        cmd1 = [
            self.ffmpeg, "-y",
            "-i", video_path,
            "-vn",
            "-filter:a", f"volume={original_volume}",
            "-acodec", "pcm_s16le",
            temp_low,
        ]
        self._run_cmd(cmd1, "Lower original audio volume")

        # Bước 2: Tạo file audio tổng hợp với từng segment lồng tiếng
        temp_segments = []
        for idx, seg in enumerate(dubbed_audio_paths):
            seg_output = os.path.join(
                MEDIA_DIR, f"temp_seg_{idx}_{os.getpid()}.wav"
            )
            # Tạo silent pad trước để đẩy audio vào đúng timestamp
            cmd_seg = [
                self.ffmpeg, "-y",
                "-i", seg["path"],
                "-af",
                f"adelay={int(seg['start']*1000)}|{int(seg['start']*1000)}",
                seg_output,
            ]
            self._run_cmd(cmd_seg, f"Position segment {idx} at {seg['start']}s")
            temp_segments.append(seg_output)

        # Bước 3: Trộn tất cả audio tracks
        mix_inputs = [temp_low] + temp_segments
        mix_filter = f"amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=2"

        temp_mix = os.path.join(MEDIA_DIR, f"temp_mix_{os.getpid()}.wav")
        cmd_mix = [self.ffmpeg, "-y"]
        for inp in mix_inputs:
            cmd_mix.extend(["-i", inp])
        cmd_mix.extend([
            "-filter_complex", mix_filter,
            "-ac", "2",
            temp_mix,
        ])
        self._run_cmd(cmd_mix, "Mix audio tracks")

        # Bước 4: Ghép audio mới vào video (giữ video gốc, thay audio)
        cmd_final = [
            self.ffmpeg, "-y",
            "-i", video_path,
            "-i", temp_mix,
            "-c:v", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            output_path,
        ]
        self._run_cmd(cmd_final, "Final audio mix")

        # Dọn temp files
        for f in [temp_low, temp_mix] + temp_segments:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass

        return output_path

    def get_video_duration(self, video_path: str) -> float:
        """Lấy duration video bằng FFprobe."""
        cmd = [
            self.ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
        return 0.0

    def get_video_resolution(self, video_path: str) -> tuple[int, int]:
        """Lấy độ phân giải (width, height)."""
        cmd = [
            self.ffprobe, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(",")
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        return (0, 0)

    def adjust_colors(self, input_path: str, output_path: str,
                      brightness: float = 0.0, contrast: float = 1.0,
                      saturation: float = 1.0) -> str:
        """Điều chỉnh màu sắc: brightness, contrast, saturation."""
        filters = []
        if brightness != 0.0:
            filters.append(f"eq=brightness={brightness}")
        if contrast != 1.0 or saturation != 1.0:
            curr = f"eq=contrast={contrast}:saturation={saturation}"
            if not filters:
                filters.append(curr)
        vf = ",".join(filters) if filters else "copy"
        cmd = [self.ffmpeg, "-y", "-i", input_path, "-vf", vf, "-c:a", "copy", output_path]
        self._run_cmd(cmd, "Adjust colors")
        return output_path

    def rotate_video(self, input_path: str, output_path: str, angle: int = 90) -> str:
        """Xoay video (90, 180, 270)."""
        transposes = {90: 1, 180: 2, 270: 3, -90: 3}
        t = transposes.get(angle, 1)
        cmd = [self.ffmpeg, "-y", "-i", input_path, "-vf", f"transpose={t}", "-c:a", "copy", output_path]
        self._run_cmd(cmd, f"Rotate {angle}")
        return output_path

    def crop_video(self, input_path: str, output_path: str,
                   top: int = 0, bottom: int = 0, left: int = 0, right: int = 0) -> str:
        """Cắt viền video."""
        if not any([top, bottom, left, right]):
            return input_path
        w, h = self.get_video_resolution(input_path)
        new_w = max(w - left - right, 1)
        new_h = max(h - top - bottom, 1)
        cmd = [self.ffmpeg, "-y", "-i", input_path,
               "-vf", f"crop={new_w}:{new_h}:{left}:{top}",
               "-c:a", "copy", output_path]
        self._run_cmd(cmd, f"Crop {top}t {bottom}b {left}l {right}r")
        return output_path

    def burn_subtitles(self, input_path: str, output_path: str,
                       subtitles: list[dict], font_size: int = 24) -> str:
        """Đốt phụ đề vào video bằng FFmpeg drawtext (hỗ trợ tiếng Việt)."""
        w, h = self.get_video_resolution(input_path)
        if not w or not h:
            w, h = 1080, 1920
        font = r"C:\Windows\Fonts\arial.ttf"
        pos_y = int(h * 0.85)
        filters = []
        for sub in subtitles:
            text = sub.get("text", "")
            start = float(sub["start"])
            duration = float(sub["end"]) - start
            if not text.strip() or duration <= 0:
                continue
            safe = text.replace(":", "\\:").replace("'", "\\'").replace("\n", " ").replace("[", "\\[").replace("]", "\\]")
            filters.append(
                f"drawtext=text='{safe}':fontfile={font}:"
                f"fontsize={font_size}:fontcolor=white:borderw=2:bordercolor=black:"
                f"x=(w-text_w)/2:y={pos_y}:"
                f"enable='between(t,{start},{start + duration})'"
            )
        if not filters:
            return input_path
        cmd = [self.ffmpeg, "-y", "-i", input_path, "-vf", ",".join(filters), "-c:a", "copy", output_path]
        self._run_cmd(cmd, "Burn subtitles")
        return output_path

    def _run_cmd(self, cmd: list[str], description: str = ""):
        """Chạy FFmpeg command và log kết quả."""
        logger.info(f"🎬 {description}: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600  # 10 phút max
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip() or "Unknown FFmpeg error"
                logger.error(f"❌ {description} failed: {error_msg}")
                raise RuntimeError(f"FFmpeg {description} thất bại: {error_msg}")
            logger.info(f"✅ {description} thành công.")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"FFmpeg {description} timeout (>10 phút)")
