"""Homepath preparation and com_pipefile discovery."""

from __future__ import annotations

import os
import platform
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .commands import CONFIG_NAME, DEMO_NAME, GAME_DIR, PIPE_NAME
from .config_writer import write_review_files


class PipeError(RuntimeError):
    """Base class for pipe discovery/control failures."""


class PipeUnsupportedError(PipeError):
    """Raised when the current platform cannot use OpenMoHAA pipe control."""


class PipeTimeoutError(PipeError):
    """Raised when the OpenMoHAA pipe does not appear in time."""


class PipeNotFifoError(PipeError):
    """Raised when the expected pipe path exists but is not a FIFO."""


class PollableProcess(Protocol):
    def poll(self) -> int | None:
        ...


@dataclass(frozen=True)
class PreparedHomepath:
    homepath: Path
    main_dir: Path
    demos_dir: Path
    demo_path: Path
    config_path: Path
    autoexec_path: Path
    menu_path: Path
    hud_ui_path: Path
    qconsole_log_path: Path
    pipe_path: Path
    screenshots_dir: Path
    videos_dir: Path
    xray_pk3_path: Path | None = None


def expected_pipe_path(homepath: Path, pipe_name: str = PIPE_NAME, game_dir: str = GAME_DIR) -> Path:
    return Path(homepath) / game_dir / pipe_name


def default_xray_pk3_path() -> Path:
    return Path(__file__).resolve().parent.parent / "custom_pk3" / "zzz-Dark_Sniper_zztoggleskin_fix.pk3"


def prepare_homepath(
    demo_file: Path | str,
    temp_dir: Path | str | None = None,
    xray_enabled: bool = False,
    xray_source: Path | str | None = None,
) -> PreparedHomepath:
    source_demo = Path(demo_file).expanduser()
    if not source_demo.is_file():
        raise FileNotFoundError(f"Demo file does not exist: {source_demo}")

    parent_temp = Path(temp_dir).expanduser() if temp_dir else None
    if parent_temp:
        parent_temp.mkdir(parents=True, exist_ok=True)
        homepath = Path(tempfile.mkdtemp(prefix="moh-arena-review-", dir=str(parent_temp)))
    else:
        homepath = Path(tempfile.mkdtemp(prefix="moh-arena-review-"))

    main_dir = homepath / GAME_DIR
    demos_dir = main_dir / "demos"
    screenshots_dir = main_dir / "screenshots"
    videos_dir = main_dir / "videos"
    for directory in (demos_dir, screenshots_dir, videos_dir):
        directory.mkdir(parents=True, exist_ok=True)

    demo_path = demos_dir / DEMO_NAME
    shutil.copy2(source_demo, demo_path)

    config_path, autoexec_path, menu_path, hud_ui_path = write_review_files(main_dir)
    qconsole_log_path = main_dir / "qconsole.log"
    qconsole_log_path.write_text("", encoding="utf-8")
    xray_pk3_path = None
    if xray_enabled:
        source_pk3 = Path(xray_source).expanduser() if xray_source else default_xray_pk3_path()
        if not source_pk3.is_file():
            raise FileNotFoundError(f"X-ray pk3 does not exist: {source_pk3}")
        xray_pk3_path = main_dir / source_pk3.name
        shutil.copy2(source_pk3, xray_pk3_path)

    return PreparedHomepath(
        homepath=homepath,
        main_dir=main_dir,
        demos_dir=demos_dir,
        demo_path=demo_path,
        config_path=config_path,
        autoexec_path=autoexec_path,
        menu_path=menu_path,
        hud_ui_path=hud_ui_path,
        qconsole_log_path=qconsole_log_path,
        pipe_path=expected_pipe_path(homepath),
        screenshots_dir=screenshots_dir,
        videos_dir=videos_dir,
        xray_pk3_path=xray_pk3_path,
    )


def find_pipe(
    homepath: Path | str,
    pipe_name: str = PIPE_NAME,
    game_dir: str = GAME_DIR,
    timeout: float = 15.0,
    poll_interval: float = 0.1,
    process: PollableProcess | None = None,
) -> Path:
    if platform.system().lower().startswith("win"):
        raise PipeUnsupportedError("OpenMoHAA com_pipefile FIFO control is not available on Windows.")

    pipe_path = expected_pipe_path(Path(homepath), pipe_name, game_dir)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise PipeTimeoutError("OpenMoHAA exited before creating the com_pipefile FIFO.")
        if pipe_path.exists():
            mode = os.stat(pipe_path).st_mode
            if not stat.S_ISFIFO(mode):
                raise PipeNotFifoError(f"Expected FIFO at {pipe_path}, but found another file type.")
            return pipe_path
        time.sleep(poll_interval)

    raise PipeTimeoutError(f"Timed out waiting for OpenMoHAA pipe: {pipe_path}")
