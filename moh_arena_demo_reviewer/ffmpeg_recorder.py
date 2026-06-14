"""FFmpeg-based screen recording for demo review sessions."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


LogCallback = Callable[[str], None]


class FfmpegRecorderError(RuntimeError):
    """Raised when FFmpeg recording cannot start or stop cleanly."""


@dataclass(frozen=True)
class CaptureRegion:
    x: int
    y: int
    width: int
    height: int
    screen_index: int = 0

    def even_sized(self) -> "CaptureRegion":
        return CaptureRegion(
            self.x,
            self.y,
            max(2, self.width - (self.width % 2)),
            max(2, self.height - (self.height % 2)),
            self.screen_index,
        )


def find_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def build_ffmpeg_command(
    ffmpeg_path: str,
    output_path: Path | str,
    region: CaptureRegion,
    *,
    platform_name: str | None = None,
    display: str | None = None,
    framerate: int = 30,
    crf: int = 28,
    preset: str = "veryfast",
) -> list[str]:
    system = (platform_name or platform.system()).lower()
    capture = region.even_sized()
    output = str(output_path)
    common = [
        ffmpeg_path,
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
    ]
    encode = [
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        output,
    ]

    if system == "darwin":
        return [
            *common,
            "-f",
            "avfoundation",
            "-framerate",
            str(framerate),
            "-capture_cursor",
            "0",
            "-i",
            f"Capture screen {capture.screen_index}:none",
            "-vf",
            f"crop={capture.width}:{capture.height}:{capture.x}:{capture.y}",
            *encode,
        ]

    if system == "windows":
        return [
            *common,
            "-f",
            "gdigrab",
            "-framerate",
            str(framerate),
            "-offset_x",
            str(capture.x),
            "-offset_y",
            str(capture.y),
            "-video_size",
            f"{capture.width}x{capture.height}",
            "-i",
            "desktop",
            *encode,
        ]

    if system == "linux":
        x_display = display or os.environ.get("DISPLAY")
        if not x_display:
            raise FfmpegRecorderError("FFmpeg x11grab recording requires DISPLAY on Linux/X11.")
        return [
            *common,
            "-f",
            "x11grab",
            "-framerate",
            str(framerate),
            "-video_size",
            f"{capture.width}x{capture.height}",
            "-i",
            f"{x_display}+{capture.x},{capture.y}",
            *encode,
        ]

    raise FfmpegRecorderError(f"FFmpeg recording is not configured for platform: {platform_name or platform.system()}")


class FfmpegRecorder:
    def __init__(self, log_callback: LogCallback | None = None) -> None:
        self._log_callback = log_callback
        self.process: subprocess.Popen[bytes] | None = None
        self.output_path: Path | None = None
        self.command: list[str] = []

    @property
    def is_recording(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, output_path: Path | str, region: CaptureRegion) -> Path:
        if self.is_recording:
            raise FfmpegRecorderError("FFmpeg is already recording.")

        ffmpeg_path = find_ffmpeg()
        if not ffmpeg_path:
            raise FfmpegRecorderError("FFmpeg was not found on PATH. Install ffmpeg to enable recording.")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        self.command = build_ffmpeg_command(ffmpeg_path, output, region)
        self._log(f"Starting FFmpeg recording: {subprocess.list2cmdline(self.command)}")
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self.output_path = output
        return output

    def stop(self) -> None:
        if not self.process:
            return
        if self.is_recording:
            if self.process.stdin:
                try:
                    self.process.stdin.write(b"q\n")
                    self.process.stdin.flush()
                except OSError:
                    pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._log("FFmpeg did not stop after q; terminating.")
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._log("FFmpeg did not terminate; killing.")
                    self.process.kill()
        stderr = self.stderr_text()
        if stderr:
            self._log(f"FFmpeg: {stderr}")
        self.process = None

    def stderr_text(self) -> str:
        if not self.process or not self.process.stderr:
            return ""
        try:
            data = self.process.stderr.read() or b""
        except OSError:
            return ""
        text = data.decode("utf-8", errors="replace").strip()
        return "\n".join(line for line in text.splitlines()[-8:] if line.strip())

    def _log(self, message: str) -> None:
        if self._log_callback:
            self._log_callback(message)
