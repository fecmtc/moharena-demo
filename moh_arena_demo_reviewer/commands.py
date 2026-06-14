"""Canonical OpenMoHAA console commands used by the reviewer."""

from __future__ import annotations

import re

DEMO_NAME = "review.dm_8"
DEMO_COMMAND_NAME = "review"
GAME_DIR = "main"
PIPE_NAME = "moh_arena_pipe"
CONFIG_NAME = "moh_arena_demo_review.cfg"
MENU_NAME = "moh_arena_demo_review"
PAUSE_TIMESCALE = "0.0001"
SPEEDS = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0)
REWIND_OFFSETS = (5, 10, 30, 60, 300, 600, 1800)


def format_speed(speed: float) -> str:
    if speed <= 0:
        raise ValueError("speed must be greater than zero")
    return f"{speed:g}"


def pause_command() -> str:
    return f"set timescale {PAUSE_TIMESCALE}; set cl_freezeDemo 1"


def play_command(speed: float = 1.0) -> str:
    return f"set timescale {format_speed(speed)}; set cl_freezeDemo 0"


def set_speed_command(speed: float) -> str:
    return play_command(speed)


def toggle_third_person_command() -> str:
    return "toggle cg_3rd_person"


def set_third_person_command(enabled: bool) -> str:
    return f"set cg_3rd_person {1 if enabled else 0}"


def show_scores_command() -> str:
    return "+scores"


def hide_scores_command() -> str:
    return "-scores"


def restart_demo_command(demo_name: str = DEMO_COMMAND_NAME) -> str:
    return f"demo {demo_name}"


def screenshot_command() -> str:
    return "screenshot"


def sanitize_video_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "moh_arena_clip"


def start_video_command(name: str = "moh_arena_clip") -> str:
    return f"video {sanitize_video_name(name)}"


def stop_video_command() -> str:
    return "stopvideo"


def quit_command() -> str:
    return "quit"


def parse_timestamp_seconds(value: str) -> float:
    value = value.strip()
    if not value:
        raise ValueError("Enter an approximate seek time, for example 02:30.")
    parts = value.split(":")
    try:
        if len(parts) == 1:
            seconds = float(parts[0])
        elif len(parts) == 2:
            minutes = int(parts[0])
            seconds = minutes * 60 + float(parts[1])
        elif len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = hours * 3600 + minutes * 60 + float(parts[2])
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError("Use seconds, mm:ss, or hh:mm:ss for approximate seek.") from exc
    if seconds < 0:
        raise ValueError("Approximate seek time must be zero or greater.")
    return seconds


def format_timestamp(seconds_total: float) -> str:
    minutes_total, seconds = divmod(seconds_total, 60.0)
    hours, minutes = divmod(int(minutes_total), 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:04.1f}"
    return f"{minutes:02d}:{seconds:04.1f}"
