"""Launch and control OpenMoHAA through com_pipefile."""

from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .commands import (
    CONFIG_NAME,
    DEMO_COMMAND_NAME,
    GAME_DIR,
    PIPE_NAME,
    hide_scores_command,
    pause_command,
    play_command,
    quit_command,
    restart_demo_command,
    screenshot_command,
    set_third_person_command,
    set_speed_command,
    show_scores_command,
    start_video_command,
    stop_video_command,
    toggle_third_person_command,
)
from .paths import PreparedHomepath, find_pipe, prepare_homepath

LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class LaunchConfig:
    executable_path: Path
    demo_path: Path
    temp_dir: Path | None = None
    xray_enabled: bool = False
    r_mode: int = -1
    width: int = 1280
    height: int = 720
    pipe_timeout: float = 15.0


def infer_basepath_from_executable(executable_path: Path | str) -> Path:
    executable = Path(executable_path).expanduser()
    if executable.suffix == ".app":
        return executable.parent

    parents = list(executable.parents)
    for parent in parents:
        if parent.suffix == ".app":
            return parent.parent

    return executable.parent


def strip_terminal_controls(text: str) -> str:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"(?:\x08 ?)+", "", text)
    return "".join(ch for ch in text if ch == "\t" or ch >= " ")


def _window_value(window: dict[Any, Any], key: str, default: Any = None) -> Any:
    if key in window:
        return window[key]
    for candidate_key, value in window.items():
        if str(candidate_key) == key:
            return value
    return default


def _process_descendant_pids(root_pid: int) -> set[int]:
    pids = {root_pid}
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid="],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return pids

    children_by_parent: dict[int, list[int]] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid, parent_pid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        children_by_parent.setdefault(parent_pid, []).append(pid)

    pending = [root_pid]
    while pending:
        parent_pid = pending.pop()
        for child_pid in children_by_parent.get(parent_pid, []):
            if child_pid not in pids:
                pids.add(child_pid)
                pending.append(child_pid)
    return pids


def _bounds_from_quartz_windows(
    windows: list[dict[Any, Any]],
    pids: int | set[int],
    owner_name_fragments: tuple[str, ...] = (),
) -> tuple[int, int, int, int] | None:
    pid_set = {pids} if isinstance(pids, int) else pids
    name_fragments = tuple(fragment.lower() for fragment in owner_name_fragments if fragment)
    best: tuple[int, int, int, int] | None = None
    best_area = 0
    for window in windows:
        owner_pid = int(_window_value(window, "kCGWindowOwnerPID", -1) or -1)
        owner_name = str(_window_value(window, "kCGWindowOwnerName", "") or "").lower()
        owner_matches = owner_pid in pid_set or any(fragment in owner_name for fragment in name_fragments)
        if not owner_matches:
            continue
        if int(_window_value(window, "kCGWindowLayer", 0) or 0) != 0:
            continue
        if not bool(_window_value(window, "kCGWindowIsOnscreen", True)):
            continue
        if float(_window_value(window, "kCGWindowAlpha", 1.0) or 0.0) <= 0:
            continue

        bounds = _window_value(window, "kCGWindowBounds")
        if not isinstance(bounds, dict):
            continue
        try:
            left = int(round(float(bounds["X"])))
            top = int(round(float(bounds["Y"])))
            width = int(round(float(bounds["Width"])))
            height = int(round(float(bounds["Height"])))
        except (KeyError, TypeError, ValueError):
            continue
        if width < 64 or height < 64:
            continue

        area = width * height
        if area > best_area:
            best_area = area
            best = (left, top, left + width, top + height)
    return best


def build_openmohaa_argv(
    executable_path: Path | str,
    basepath: Path | str,
    homepath: Path | str,
    width: int = 1280,
    height: int = 720,
    r_mode: int = -1,
    pipe_name: str = PIPE_NAME,
) -> list[str]:
    return [
        str(executable_path),
        "+set",
        "fs_basepath",
        str(basepath),
        "+set",
        "fs_homepath",
        str(homepath),
        "+set",
        "r_fullscreen",
        "0",
        "+set",
        "r_mode",
        str(r_mode),
        "+set",
        "r_customwidth",
        str(width),
        "+set",
        "r_customheight",
        str(height),
        "+set",
        "r_noborder",
        "0",
        "+set",
        "in_nograb",
        "1",
        "+set",
        "com_pipefile",
        pipe_name,
        "+set",
        "cheats",
        "1",
        "+set",
        "sv_cheats",
        "1",
        "+set",
        "timedemo",
        "0",
        "+set",
        "timescale",
        "1",
        "+set",
        "cl_freezeDemo",
        "0",
        "+exec",
        CONFIG_NAME,
        "+demo",
        DEMO_COMMAND_NAME,
    ]


class OpenMohaaController:
    def __init__(self, log_callback: LogCallback | None = None) -> None:
        self._log_callback = log_callback
        self.process: subprocess.Popen[str] | None = None
        self.prepared: PreparedHomepath | None = None
        self.basepath: Path | None = None
        self.executable_path: Path | None = None
        self.pipe_path: Path | None = None
        self.argv: list[str] = []
        self._xray_cleaned = False
        self._quartz_import_warning_logged = False
        self._quartz_no_window_warning_logged = False

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def launch(self, config: LaunchConfig) -> PreparedHomepath:
        if self.is_running:
            raise RuntimeError("OpenMoHAA is already running.")
        executable = Path(config.executable_path).expanduser()
        basepath = infer_basepath_from_executable(executable)
        self.basepath = basepath
        self.executable_path = executable
        self._quartz_import_warning_logged = False
        self._quartz_no_window_warning_logged = False
        if not executable.is_file():
            raise FileNotFoundError(f"OpenMoHAA executable does not exist: {executable}")
        if not basepath.exists():
            raise FileNotFoundError(f"Inferred MOHAA basepath does not exist: {basepath}")

        self.prepared = prepare_homepath(config.demo_path, config.temp_dir, xray_enabled=config.xray_enabled)
        self._xray_cleaned = False
        self.argv = build_openmohaa_argv(
            executable,
            basepath,
            self.prepared.homepath,
            r_mode=config.r_mode,
            width=config.width,
            height=config.height,
        )
        self._log(f"Inferred fs_basepath: {basepath}")
        if self.prepared.xray_pk3_path:
            self._log(f"X-ray pk3 enabled: {self.prepared.xray_pk3_path}")
        self._log(f"Launching: {subprocess.list2cmdline(self.argv)}")
        self.process = subprocess.Popen(
            self.argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.pipe_path = find_pipe(
            self.prepared.homepath,
            timeout=config.pipe_timeout,
            process=self.process,
        )
        self._log(f"Pipe ready: {self.pipe_path}")
        return self.prepared

    def video_output_dir(self) -> Path:
        if not self.basepath:
            raise RuntimeError("OpenMoHAA basepath is not known yet.")
        videos_dir = self.basepath / GAME_DIR / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)
        return videos_dir

    def read_output_lines(self) -> list[str]:
        if not self.process or not self.process.stdout:
            return []
        lines: list[str] = []
        # Qt uses this from a timer; keep it conservative and avoid blocking.
        fd = self.process.stdout.fileno()
        try:
            import select

            while True:
                ready, _, _ = select.select([fd], [], [], 0)
                if not ready:
                    break
                line = self.process.stdout.readline()
                if not line:
                    break
                clean_line = strip_terminal_controls(line.rstrip("\n"))
                if clean_line:
                    lines.append(clean_line)
        except (OSError, ValueError):
            return lines
        return lines

    def stop(self) -> None:
        if not self.process:
            return
        if self.is_running:
            try:
                self.send_command(quit_command())
            except Exception as exc:  # noqa: BLE001 - best-effort shutdown path
                self._log(f"Could not send quit through pipe: {exc}")
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._log("OpenMoHAA did not exit after quit; terminating process.")
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._log("OpenMoHAA did not terminate; killing process.")
                    self.process.kill()
        self.cleanup_xray_pk3()
        self.process = None
        self.pipe_path = None

    def cleanup_xray_pk3(self) -> None:
        if self._xray_cleaned or not self.prepared or not self.prepared.xray_pk3_path:
            return
        try:
            self.prepared.xray_pk3_path.unlink(missing_ok=True)
            self._log(f"Removed x-ray pk3: {self.prepared.xray_pk3_path}")
        except OSError as exc:
            self._log(f"Could not remove x-ray pk3: {exc}")
        finally:
            self._xray_cleaned = True

    def send_command(self, command: str) -> None:
        if not self.is_running:
            raise RuntimeError("OpenMoHAA is not running.")
        if not self.pipe_path:
            raise RuntimeError("OpenMoHAA pipe is not ready.")
        payload = command.rstrip("\r\n") + "\n"
        flags = os.O_WRONLY
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        fd = os.open(self.pipe_path, flags)
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        self._log(f"> {command}")

    def play(self, speed: float = 1.0) -> None:
        self.send_command(play_command(speed))

    def pause(self) -> None:
        self.send_command(pause_command())

    def set_speed(self, speed: float) -> None:
        self.send_command(set_speed_command(speed))

    def toggle_third_person(self) -> None:
        self.send_command(toggle_third_person_command())

    def set_third_person(self, enabled: bool) -> None:
        self.send_command(set_third_person_command(enabled))

    def show_scores(self) -> None:
        self.send_command(show_scores_command())

    def hide_scores(self) -> None:
        self.send_command(hide_scores_command())

    def restart_demo(self) -> None:
        self.send_command(restart_demo_command())

    def screenshot(self) -> None:
        self.send_command(screenshot_command())

    def start_video(self, name: str = "moh_arena_clip") -> None:
        self.send_command(start_video_command(name))

    def stop_video(self) -> None:
        self.send_command(stop_video_command())

    def quit(self) -> None:
        self.send_command(quit_command())

    def move_window(self, x: int, y: int, width: int | None = None, height: int | None = None) -> tuple[int, int, int, int] | None:
        if not self.process or platform.system() != "Darwin":
            return None

        bounds_script = ""
        if width is not None and height is not None:
            bounds_script = f"set size of window 1 to {{{width}, {height}}}\n"

        script = f"""
        tell application "System Events"
          set matchingProcesses to processes whose unix id is {self.process.pid}
          if (count of matchingProcesses) is 0 then
            return "NO_PROCESS"
          end if
          set targetProcess to item 1 of matchingProcesses
          tell targetProcess
            if (count of windows) is 0 then
              return "NO_WINDOWS"
            end if
            set position of window 1 to {{{x}, {y}}}
            {bounds_script}
            set windowBounds to bounds of window 1
            return "OK|" & (item 1 of windowBounds as text) & "," & (item 2 of windowBounds as text) & "," & (item 3 of windowBounds as text) & "," & (item 4 of windowBounds as text)
          end tell
        end tell
        """
        response = self._run_window_script(script, "position")
        if not response:
            return None
        return self._parse_window_bounds_response(response, "position")

    def get_window_bounds(self) -> tuple[int, int, int, int] | None:
        if not self.process or platform.system() != "Darwin":
            return None

        quartz_bounds = self._get_window_bounds_quartz()
        if quartz_bounds:
            return quartz_bounds

        script = f"""
        tell application "System Events"
          set matchingProcesses to processes whose unix id is {self.process.pid}
          if (count of matchingProcesses) is 0 then
            return "NO_PROCESS"
          end if
          set targetProcess to item 1 of matchingProcesses
          tell targetProcess
            if (count of windows) is 0 then
              return "NO_WINDOWS"
            end if
            set windowBounds to bounds of window 1
            return "OK|" & (item 1 of windowBounds as text) & "," & (item 2 of windowBounds as text) & "," & (item 3 of windowBounds as text) & "," & (item 4 of windowBounds as text)
          end tell
        end tell
        """
        response = self._run_window_script(script, "inspect")
        if not response:
            return None
        return self._parse_window_bounds_response(response, "inspect")

    def _get_window_bounds_quartz(self) -> tuple[int, int, int, int] | None:
        if not self.process:
            return None
        try:
            import Quartz  # type: ignore[import-not-found]
        except ImportError as exc:
            if not self._quartz_import_warning_logged:
                self._log(f"PyObjC Quartz is not available in this Python environment: {exc}")
                self._quartz_import_warning_logged = True
            return None

        try:
            options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
            windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID) or []
        except Exception as exc:
            if not self._quartz_no_window_warning_logged:
                self._log(f"Could not enumerate macOS windows through Quartz: {exc}")
                self._quartz_no_window_warning_logged = True
            return None

        candidate_pids = _process_descendant_pids(self.process.pid)
        executable_stem = self.executable_path.stem.lower() if self.executable_path else ""
        owner_fragments = tuple(fragment for fragment in ("openmohaa", executable_stem) if fragment)
        bounds = _bounds_from_quartz_windows(list(windows), candidate_pids, owner_fragments)
        if bounds:
            self._quartz_no_window_warning_logged = False
            return bounds

        if not self._quartz_no_window_warning_logged:
            visible_windows = []
            for window in list(windows):
                owner_pid = int(_window_value(window, "kCGWindowOwnerPID", -1) or -1)
                owner_name = str(_window_value(window, "kCGWindowOwnerName", "") or "")
                if owner_pid in candidate_pids or "mohaa" in owner_name.lower():
                    visible_windows.append(f"{owner_name or '<unnamed>'}[pid={owner_pid}]")
            suffix = f" Nearby windows: {', '.join(visible_windows[:5])}" if visible_windows else ""
            self._log(
                "Quartz could not find an on-screen OpenMoHAA window. "
                f"Checked pid(s): {sorted(candidate_pids)}; owner names: {owner_fragments}.{suffix}"
            )
            self._quartz_no_window_warning_logged = True
        return None

    def _run_window_script(self, script: str, action: str) -> str | None:
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._log(f"Could not {action} OpenMoHAA window: {exc}")
            return None

        if result.returncode != 0:
            message = strip_terminal_controls((result.stderr or result.stdout).strip())
            self._log(f"Could not {action} OpenMoHAA window: {message}")
            return None
        return strip_terminal_controls((result.stdout or "").strip())

    def _parse_window_bounds_response(self, response: str, action: str) -> tuple[int, int, int, int] | None:
        if not response.startswith("OK|"):
            if response and response != "NO_WINDOWS":
                self._log(f"Could not {action} OpenMoHAA window: {response}")
            return None
        try:
            bounds = tuple(int(part.strip()) for part in response.removeprefix("OK|").split(","))
        except ValueError:
            self._log(f"Could not parse OpenMoHAA window bounds: {response}")
            return None
        if len(bounds) != 4:
            self._log(f"Could not parse OpenMoHAA window bounds: {response}")
            return None
        return bounds

    def _log(self, message: str) -> None:
        if self._log_callback:
            self._log_callback(message)
