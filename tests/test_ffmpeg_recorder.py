from pathlib import Path

import pytest

from moh_arena_demo_reviewer.ffmpeg_recorder import (
    CaptureRegion,
    FfmpegRecorderError,
    build_ffmpeg_command,
)


def test_build_ffmpeg_command_macos_uses_avfoundation_crop() -> None:
    command = build_ffmpeg_command(
        "/usr/local/bin/ffmpeg",
        Path("/tmp/review.mp4"),
        CaptureRegion(10, 20, 641, 481),
        platform_name="Darwin",
    )

    assert command[:5] == ["/usr/local/bin/ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"]
    assert "avfoundation" in command
    assert "Capture screen 0:none" in command
    assert "crop=640:480:10:20" in command
    assert command[-1] == "/tmp/review.mp4"
    assert command[command.index("-crf") + 1] == "28"
    assert command[command.index("-preset") + 1] == "veryfast"


def test_build_ffmpeg_command_macos_uses_capture_screen_index() -> None:
    command = build_ffmpeg_command(
        "ffmpeg",
        "/tmp/review.mp4",
        CaptureRegion(10, 20, 640, 480, screen_index=2),
        platform_name="Darwin",
    )

    assert "Capture screen 2:none" in command


def test_build_ffmpeg_command_linux_uses_x11grab_display() -> None:
    command = build_ffmpeg_command(
        "ffmpeg",
        "/tmp/review.mp4",
        CaptureRegion(100, 200, 800, 600),
        platform_name="Linux",
        display=":1",
    )

    assert "x11grab" in command
    assert "800x600" in command
    assert ":1+100,200" in command


def test_build_ffmpeg_command_linux_requires_display(monkeypatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)

    with pytest.raises(FfmpegRecorderError):
        build_ffmpeg_command("ffmpeg", "/tmp/review.mp4", CaptureRegion(0, 0, 800, 600), platform_name="Linux")


def test_build_ffmpeg_command_windows_uses_gdigrab() -> None:
    command = build_ffmpeg_command(
        "ffmpeg.exe",
        "C:/tmp/review.mp4",
        CaptureRegion(5, 6, 320, 240),
        platform_name="Windows",
    )

    assert "gdigrab" in command
    assert command[command.index("-offset_x") + 1] == "5"
    assert command[command.index("-offset_y") + 1] == "6"
    assert command[command.index("-video_size") + 1] == "320x240"
    assert command[-1] == "C:/tmp/review.mp4"
