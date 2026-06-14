"""PySide6 desktop GUI for controlling OpenMoHAA demo playback."""

from __future__ import annotations

import sys
import platform
import subprocess
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSettings, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from .commands import REWIND_OFFSETS, SPEEDS, format_timestamp, parse_timestamp_seconds, sanitize_video_name
from .ffmpeg_recorder import CaptureRegion, FfmpegRecorder
from .openmohaa_controller import LaunchConfig, OpenMohaaController

R_MODE_OPTIONS = [
    ("Custom (-1)", -1),
    ("512 x 384 (r_mode 3)", 3),
    ("640 x 480 (r_mode 4)", 4),
    ("800 x 600 (r_mode 5)", 5),
    ("1024 x 768 (r_mode 6)", 6),
    ("1152 x 864 (r_mode 7)", 7),
    ("1280 x 1024 (r_mode 8)", 8),
    ("1600 x 1200 (r_mode 9)", 9),
]
R_MODE_SIZES = {
    3: (512, 384),
    4: (640, 480),
    5: (800, 600),
    6: (1024, 768),
    7: (1152, 864),
    8: (1280, 1024),
    9: (1600, 1200),
}


class LaunchWorker(QThread):
    launched = Signal(object)
    failed = Signal(str)
    log = Signal(str)

    def __init__(self, controller: OpenMohaaController, config: LaunchConfig) -> None:
        super().__init__()
        self.controller = controller
        self.config = config

    def run(self) -> None:
        try:
            prepared = self.controller.launch(self.config)
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")
            return
        self.launched.emit(prepared)


class PathPicker(QWidget):
    def __init__(self, label: str, mode: str) -> None:
        super().__init__()
        self.mode = mode
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(label)
        self.edit = QLineEdit()
        self.button = QPushButton("Browse")
        self.button.clicked.connect(self.browse)
        layout.addWidget(self.label)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    def text(self) -> str:
        return self.edit.text().strip()

    def set_text(self, value: str) -> None:
        self.edit.setText(value)

    def browse(self) -> None:
        current = self.text() or str(Path.home())
        if self.mode == "file":
            path, _ = QFileDialog.getOpenFileName(self, self.label.text(), current)
        elif self.mode == "demo":
            path, _ = QFileDialog.getOpenFileName(
                self,
                self.label.text(),
                current,
                "MOHAA demos (*.dm_* *.demo_aa);;All files (*)",
            )
        else:
            path = QFileDialog.getExistingDirectory(self, self.label.text(), current)
        if path:
            self.set_text(path)


class RecordingRegionSelector(QWidget):
    region_selected = Signal(tuple)
    canceled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Select Recording Region")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._origin: QPoint | None = None
        self._selection = QRect()

        geometry = QRect()
        for screen in QApplication.screens():
            geometry = screen.geometry() if geometry.isNull() else geometry.united(screen.geometry())
        self.setGeometry(geometry)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.raise_()
        self.activateWindow()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
        painter.setPen(QPen(QColor(245, 214, 107), 2))
        painter.drawText(24, 36, "Drag around the OpenMoHAA window. Press Esc to cancel.")
        if not self._selection.isNull():
            selected = self._selection.normalized()
            painter.fillRect(selected, QColor(245, 214, 107, 35))
            painter.drawRect(selected)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._origin = event.position().toPoint()
        self._selection = QRect(self._origin, self._origin)
        self.update()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._origin is None:
            return
        self._selection = QRect(self._origin, event.position().toPoint()).normalized()
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        selected = QRect(self._origin, event.position().toPoint()).normalized()
        self._origin = None
        if selected.width() < 16 or selected.height() < 16:
            self.canceled.emit()
            self.close()
            return
        global_top_left = selected.topLeft() + self.geometry().topLeft()
        bounds = (
            global_top_left.x(),
            global_top_left.y(),
            global_top_left.x() + selected.width(),
            global_top_left.y() + selected.height(),
        )
        self.region_selected.emit(bounds)
        self.close()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.canceled.emit()
            self.close()
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    log_message = Signal(str)
    SEEK_FAST_SPEED = 64.0

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MoH Arena Demo Reviewer")
        self.resize(720, 300)

        self.settings = QSettings("MoH Arena", "DemoReviewer")
        self.log_message.connect(self.append_log)
        self.controller = OpenMohaaController(log_callback=self.log_message.emit)
        self.recorder = FfmpegRecorder(log_callback=self.log_message.emit)
        self.worker: LaunchWorker | None = None

        self.exe_picker = PathPicker("OpenMoHAA executable", "file")
        self.demo_picker = PathPicker("Demo file", "demo")
        self.temp_picker = PathPicker("Temp dir (optional)", "dir")
        self.xray_checkbox = QCheckBox("X-ray vision")
        self.r_mode_combo = QComboBox()
        for label, r_mode in R_MODE_OPTIONS:
            self.r_mode_combo.addItem(label, r_mode)
        self.r_mode_combo.setMinimumWidth(190)
        self.width_edit = QLineEdit("1280")
        self.height_edit = QLineEdit("720")
        self.status_label = QLabel("Not launched")
        self.status_label.setWordWrap(False)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.status_label.setMaximumHeight(24)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)

        self.launch_button = QPushButton("Launch Demo")
        self.quit_button = QPushButton("Quit")
        self.setup_toggle_button = QPushButton("Hide Setup")
        self.log_toggle_button = QPushButton("Show Log")
        self.play_pause_button = QPushButton("Pause")
        self.play_pause_button.setCheckable(True)
        self.third_button = QPushButton("3rd Person")
        self.third_button.setCheckable(True)
        self.scores_button = QPushButton("Scores")
        self.scores_button.setCheckable(True)
        self.restart_button = QPushButton("Restart")
        self.stop_button = QPushButton("Stop")
        self.screenshot_button = QPushButton("Take screenshot")
        self.select_region_button = QPushButton("Select Region")
        self.start_video_button = QPushButton("Start Rec")
        self.stop_video_button = QPushButton("Stop Rec")
        self.video_name_edit = QLineEdit("moh_arena_clip")
        self.video_status_label = QLabel("Rec: idle")
        self.video_status_label.setWordWrap(False)
        self.video_status_label.setMaximumWidth(420)
        self.timestamp_label = QLabel("Est. Time: 00:00.0")
        self.seek_edit = QLineEdit("00:00")
        self.seek_edit.setPlaceholderText("mm:ss")
        self.seek_edit.setMaximumWidth(70)
        self.seek_button = QPushButton("Approx Seek")

        self.speed_buttons: list[QPushButton] = []
        self.rewind_buttons: list[QPushButton] = []
        self.config_box: QGroupBox | None = None
        self.controls_box: QGroupBox | None = None
        self.log_box: QGroupBox | None = None
        self._demo_seconds = 0.0
        self._demo_speed = 1.0
        self._demo_paused = False
        self._demo_clock_active = False
        self._demo_clock_mark = time.monotonic()
        self._seek_generation = 0
        self._arrange_attempts = 0
        self._recording_path: Path | None = None
        self._recording_started_at: float | None = None
        self._recording_pending = False
        self._capture_bounds: tuple[int, int, int, int] | None = None
        self._capture_bounds_verified = False
        self._manual_capture_bounds: tuple[int, int, int, int] | None = None
        self._region_selector: RecordingRegionSelector | None = None
        self._last_bounds_poll = 0.0
        self._playback_geometry_restored = False
        self._playback_auto_positioned = False
        self._apply_style()
        self._build_layout()
        self._connect_signals()
        self._load_settings()
        self._set_controls_enabled(False)
        self.setup_toggle_button.setEnabled(False)
        self.log_toggle_button.setEnabled(False)

        self.output_timer = QTimer(self)
        self.output_timer.timeout.connect(self._drain_output)
        self.output_timer.start(250)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._save_settings()
        self._save_positions()
        self.recorder.stop()
        self.controller.stop()
        super().closeEvent(event)

    def _build_layout(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.config_box = QGroupBox("Launch Configuration")
        config_layout = QVBoxLayout(self.config_box)
        config_layout.setSpacing(6)
        for picker in (self.exe_picker, self.demo_picker, self.temp_picker):
            config_layout.addWidget(picker)
        config_layout.addWidget(self.xray_checkbox)

        display_row = QHBoxLayout()
        display_row.addWidget(QLabel("Resolution"))
        display_row.addWidget(self.r_mode_combo)
        display_row.addWidget(QLabel("Width"))
        display_row.addWidget(self.width_edit)
        display_row.addWidget(QLabel("Height"))
        display_row.addWidget(self.height_edit)
        display_row.addStretch(1)
        config_layout.addLayout(display_row)

        action_bar = QHBoxLayout()
        action_bar.addWidget(self.launch_button)
        action_bar.addWidget(self.quit_button)
        action_bar.addWidget(self.setup_toggle_button)
        action_bar.addWidget(self.log_toggle_button)
        action_bar.addWidget(QLabel("Status:"))
        action_bar.addWidget(self.status_label, 1)

        self.controls_box = QGroupBox("Playback Controls")
        controls = QVBoxLayout(self.controls_box)
        controls.setSpacing(6)

        primary_row = QHBoxLayout()
        primary_row.setSpacing(6)
        primary_buttons = [
            self.play_pause_button,
            self.restart_button,
            self.stop_button,
            self.third_button,
            self.scores_button,
            self.screenshot_button,
        ]
        for button in primary_buttons:
            primary_row.addWidget(button)
        primary_row.addWidget(self.timestamp_label)
        primary_row.addStretch(1)
        controls.addLayout(primary_row)

        speed_row = QHBoxLayout()
        speed_row.setSpacing(6)
        for speed in SPEEDS:
            button = QPushButton(f"{speed:g}x")
            button.setFixedWidth(64)
            button.clicked.connect(lambda checked=False, s=speed: self.set_speed(s))
            self.speed_buttons.append(button)
            speed_row.addWidget(button)
        speed_row.addStretch(1)
        controls.addLayout(speed_row)

        rewind_row = QHBoxLayout()
        rewind_row.setSpacing(6)
        for offset in REWIND_OFFSETS:
            button = QPushButton(f"-{self._format_offset_label(offset)}")
            button.setFixedWidth(64)
            button.clicked.connect(lambda checked=False, seconds=offset: self.rewind_by(seconds))
            self.rewind_buttons.append(button)
            rewind_row.addWidget(button)
        seek_box = QWidget()
        seek_layout = QHBoxLayout(seek_box)
        seek_layout.setContentsMargins(0, 0, 0, 0)
        seek_layout.setSpacing(4)
        seek_layout.addWidget(QLabel("Go to"))
        seek_layout.addWidget(self.seek_edit)
        seek_layout.addWidget(self.seek_button)
        rewind_row.addWidget(seek_box)
        rewind_row.addStretch(1)
        controls.addLayout(rewind_row)

        video_row = QHBoxLayout()
        video_row.setSpacing(6)
        video_row.addWidget(QLabel("Video"))
        video_row.addWidget(self.video_name_edit, 1)
        video_row.addWidget(self.select_region_button)
        video_row.addWidget(self.start_video_button)
        video_row.addWidget(self.stop_video_button)
        video_row.addWidget(self.video_status_label)
        video_row.addStretch(1)
        controls.addLayout(video_row)
        self.controls_box.hide()

        self.log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(self.log_box)
        log_layout.addWidget(self.log_view)
        self.log_box.hide()

        layout.addWidget(self.config_box)
        layout.addLayout(action_bar)
        layout.addWidget(self.controls_box)
        layout.addWidget(self.log_box, 1)
        self.setCentralWidget(root)

    def _connect_signals(self) -> None:
        self.launch_button.clicked.connect(self.launch_demo)
        self.quit_button.clicked.connect(self.close)
        self.setup_toggle_button.clicked.connect(self._toggle_setup)
        self.log_toggle_button.clicked.connect(self._toggle_log)
        self.r_mode_combo.currentIndexChanged.connect(self._sync_custom_resolution_enabled)
        self.play_pause_button.toggled.connect(self.set_paused)
        self.third_button.toggled.connect(self.set_third_person)
        self.scores_button.toggled.connect(self.set_scores_visible)
        self.restart_button.clicked.connect(self.restart_demo)
        self.stop_button.clicked.connect(self.stop_openmohaa)
        self.screenshot_button.clicked.connect(lambda: self._send(self.controller.screenshot))
        self.seek_button.clicked.connect(self.approx_seek)
        self.select_region_button.clicked.connect(self.select_recording_region)
        self.start_video_button.clicked.connect(self.start_video_recording)
        self.stop_video_button.clicked.connect(self.stop_video_recording)

    def launch_demo(self) -> None:
        self._save_settings()
        self._save_gui_geometry("setup")
        try:
            config = LaunchConfig(
                executable_path=Path(self.exe_picker.text()),
                demo_path=Path(self.demo_picker.text()),
                temp_dir=Path(self.temp_picker.text()) if self.temp_picker.text() else None,
                xray_enabled=self.xray_checkbox.isChecked(),
                r_mode=int(self.r_mode_combo.currentData()),
                width=self._parse_int(self.width_edit.text(), "custom width"),
                height=self._parse_int(self.height_edit.text(), "custom height"),
            )
        except Exception as exc:  # noqa: BLE001 - GUI validation boundary
            self._show_error(str(exc))
            return
        self.launch_button.setEnabled(False)
        self._set_status("Launching...")
        self.worker = LaunchWorker(self.controller, config)
        self.worker.launched.connect(self._launch_succeeded)
        self.worker.failed.connect(self._launch_failed)
        self.worker.start()

    def append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _send(self, action) -> bool:
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            self._show_error(str(exc))
            self.append_log(f"ERROR: {exc}")
            return False
        return True

    def _launch_succeeded(self, prepared) -> None:
        self._set_status("Running")
        self.append_log(f"Prepared homepath: {prepared.homepath}")
        self._reset_demo_clock()
        self.play_pause_button.blockSignals(True)
        self.play_pause_button.setChecked(False)
        self.play_pause_button.setText("Pause")
        self.play_pause_button.blockSignals(False)
        self.third_button.blockSignals(True)
        self.third_button.setChecked(False)
        self.third_button.blockSignals(False)
        self.scores_button.blockSignals(True)
        self.scores_button.setChecked(False)
        self.scores_button.blockSignals(False)
        self._set_setup_visible(False)
        self._set_log_visible(False)
        self._set_controls_enabled(True)
        self.setup_toggle_button.setEnabled(True)
        self.log_toggle_button.setEnabled(True)
        self._capture_bounds = None
        self._capture_bounds_verified = False
        self._manual_capture_bounds = None
        self._reset_video_recording_status()
        self._set_playback_visible(True)
        self._playback_geometry_restored = self._restore_gui_geometry("playback")
        self._playback_auto_positioned = self._playback_geometry_restored
        if not self._playback_geometry_restored:
            self._shrink_to_minimal()
        self._arrange_attempts = 0
        QTimer.singleShot(600, self._arrange_windows)

    def _launch_failed(self, message: str) -> None:
        self._set_status("Launch failed")
        self.append_log(f"ERROR: {message}")
        self._show_error(message.split("\n", 1)[0])
        self.controller.cleanup_xray_pk3()
        self._set_setup_visible(True)
        self._set_playback_visible(False)
        self.setup_toggle_button.setEnabled(False)
        self.log_toggle_button.setEnabled(False)
        self._reset_video_recording_status()
        self.launch_button.setEnabled(True)
        self._set_controls_enabled(False)

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in [
            self.play_pause_button,
            self.third_button,
            self.scores_button,
            self.restart_button,
            self.stop_button,
            self.screenshot_button,
            self.seek_edit,
            self.seek_button,
            self.start_video_button,
            self.stop_video_button,
            self.video_name_edit,
            self.select_region_button,
            *self.speed_buttons,
            *self.rewind_buttons,
        ]:
            widget.setEnabled(enabled)
        self.launch_button.setEnabled(not enabled)
        self.quit_button.setEnabled(True)
        if enabled and not self._recording_pending:
            self.start_video_button.setEnabled(True)
            self.stop_video_button.setEnabled(False)

    def _drain_output(self) -> None:
        if self._demo_clock_active:
            self._refresh_demo_timestamp()
        self._refresh_video_recording_status()
        for line in self.controller.read_output_lines():
            self.append_log(line)
        if self.controller.process and self.controller.process.poll() is not None:
            self._set_status(f"Exited: {self.controller.process.returncode}")
            self._save_gui_geometry("playback")
            if self._capture_bounds_verified:
                self._save_openmohaa_bounds(self._capture_bounds)
            self.recorder.stop()
            self.controller.cleanup_xray_pk3()
            self._demo_clock_active = False
            self._set_controls_enabled(False)
            self._set_setup_visible(True)
            self._set_playback_visible(False)
            self.setup_toggle_button.setEnabled(False)
            self.log_toggle_button.setEnabled(False)
            self._reset_video_recording_status()
        else:
            self._refresh_openmohaa_bounds()

    def _load_settings(self) -> None:
        self.exe_picker.set_text(self.settings.value("executable_path", "", str))
        self.demo_picker.set_text(self.settings.value("demo_path", "", str))
        self.temp_picker.set_text(self.settings.value("temp_dir", "", str))
        self.xray_checkbox.setChecked(self.settings.value("xray_enabled", False, bool))
        self._set_r_mode(int(self.settings.value("r_mode", "-1", str)))
        self.width_edit.setText(self.settings.value("width", "1280", str))
        self.height_edit.setText(self.settings.value("height", "720", str))
        self._sync_custom_resolution_enabled()
        self._restore_gui_geometry("setup")

    def _save_settings(self) -> None:
        self.settings.setValue("executable_path", self.exe_picker.text())
        self.settings.setValue("demo_path", self.demo_picker.text())
        self.settings.setValue("temp_dir", self.temp_picker.text())
        self.settings.setValue("xray_enabled", self.xray_checkbox.isChecked())
        self.settings.setValue("r_mode", str(int(self.r_mode_combo.currentData())))
        self.settings.setValue("width", self.width_edit.text().strip())
        self.settings.setValue("height", self.height_edit.text().strip())

    def _save_positions(self) -> None:
        mode = "playback" if self.controls_box and self.controls_box.isVisible() else "setup"
        self._save_gui_geometry(mode)
        self._refresh_openmohaa_bounds(force=True)
        if self._capture_bounds_verified:
            self._save_openmohaa_bounds(self._capture_bounds)

    def _save_gui_geometry(self, mode: str) -> None:
        self.settings.setValue(f"geometry/{mode}", self.saveGeometry())

    def _restore_gui_geometry(self, mode: str) -> bool:
        geometry = self.settings.value(f"geometry/{mode}")
        if not geometry:
            return False
        return bool(self.restoreGeometry(geometry))

    def _saved_openmohaa_bounds(self) -> tuple[int, int, int, int] | None:
        values: list[int] = []
        for key in ("x", "y", "w", "h"):
            raw = self.settings.value(f"openmohaa/{key}", "", str)
            try:
                values.append(int(raw))
            except (TypeError, ValueError):
                return None
        x, y, width, height = values
        if width <= 0 or height <= 0:
            return None
        return x, y, x + width, y + height

    def _save_openmohaa_bounds(self, bounds: tuple[int, int, int, int] | None) -> None:
        if not bounds:
            return
        left, top, right, bottom = bounds
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return
        self.settings.setValue("openmohaa/x", str(left))
        self.settings.setValue("openmohaa/y", str(top))
        self.settings.setValue("openmohaa/w", str(width))
        self.settings.setValue("openmohaa/h", str(height))

    def _refresh_openmohaa_bounds(self, force: bool = False) -> None:
        if not self.controller.is_running:
            return
        now = time.monotonic()
        if not force and now - self._last_bounds_poll < 2.0:
            return
        self._last_bounds_poll = now
        bounds = self.controller.get_window_bounds()
        if bounds:
            self._capture_bounds = bounds
            self._capture_bounds_verified = True
            self._save_openmohaa_bounds(bounds)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "MoH Arena Demo Reviewer", message)

    def _show_recording_error(self, message: str) -> None:
        if platform.system() != "Darwin" or "OpenMoHAA window bounds" not in message:
            self._show_error(message)
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("MoH Arena Demo Reviewer")
        box.setText(message)
        box.setInformativeText(
            "Exact window-only recording uses PyObjC/Quartz first and now checks the OpenMoHAA "
            "process, child processes, and OpenMoHAA-like window owner names.\n\n"
            "Open the log panel for the detailed detection reason. If it says Quartz is unavailable, "
            "run `python -m pip install -r requirements.txt` in the active venv, then quit and reopen. "
            "If Quartz is available but no window is found, macOS may be hiding the SDL window; check "
            "Accessibility for the app that launched this tool. FFmpeg may also require Screen "
            "Recording permission on first capture."
        )
        select_region_button = box.addButton("Select Region", QMessageBox.ButtonRole.ActionRole)
        settings_button = box.addButton("Open Accessibility Settings", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        clicked = box.clickedButton()
        if clicked == select_region_button:
            QTimer.singleShot(0, self.select_recording_region)
        elif clicked == settings_button:
            self._open_macos_accessibility_settings()

    def _open_macos_accessibility_settings(self) -> None:
        try:
            subprocess.Popen(
                ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self.append_log(f"Could not open Accessibility settings: {exc}")

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)
        self._resize_to_visible_content()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                font-size: 12px;
            }
            QMainWindow, QWidget {
                background: #202226;
                color: #e8e8e8;
            }
            QGroupBox {
                border: 1px solid #3b3f46;
                border-radius: 6px;
                margin-top: 10px;
                padding: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #d6c37a;
            }
            QLineEdit, QPlainTextEdit, QComboBox {
                background: #14161a;
                border: 1px solid #3b3f46;
                border-radius: 4px;
                padding: 5px;
                color: #f1f1f1;
            }
            QPushButton {
                background: #30343b;
                border: 1px solid #4a505a;
                border-radius: 5px;
                padding: 5px 8px;
            }
            QPushButton:hover {
                background: #3a4049;
            }
            QPushButton:pressed {
                background: #252930;
            }
            QPushButton:checked {
                background: #5a4b22;
                border-color: #c4a23a;
            }
            QPushButton:disabled {
                color: #777b83;
                background: #25272c;
                border-color: #33363d;
            }
            """
        )

    def _toggle_setup(self) -> None:
        self._set_setup_visible(not bool(self.config_box and self.config_box.isVisible()))

    def _toggle_log(self) -> None:
        self._set_log_visible(not bool(self.log_box and self.log_box.isVisible()))

    def _set_setup_visible(self, visible: bool) -> None:
        if self.config_box:
            self.config_box.setVisible(visible)
        self.setup_toggle_button.setText("Hide Setup" if visible else "Show Setup")
        self._resize_to_visible_content()

    def _set_log_visible(self, visible: bool) -> None:
        if self.log_box:
            self.log_box.setVisible(visible)
        self.log_toggle_button.setText("Hide Log" if visible else "Show Log")
        self._resize_to_visible_content()

    def _set_playback_visible(self, visible: bool) -> None:
        if self.controls_box:
            self.controls_box.setVisible(visible)
        self._resize_to_visible_content()

    def _parse_int(self, value: str, label: str) -> int:
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ValueError(f"{label} must be an integer.") from exc

    def _set_r_mode(self, r_mode: int) -> None:
        for index in range(self.r_mode_combo.count()):
            if int(self.r_mode_combo.itemData(index)) == r_mode:
                self.r_mode_combo.setCurrentIndex(index)
                return
        self.r_mode_combo.setCurrentIndex(0)

    def _sync_custom_resolution_enabled(self) -> None:
        custom = int(self.r_mode_combo.currentData()) == -1
        self.width_edit.setEnabled(custom)
        self.height_edit.setEnabled(custom)

    def _selected_game_size(self) -> tuple[int, int]:
        r_mode = int(self.r_mode_combo.currentData())
        if r_mode == -1:
            return self._parse_int(self.width_edit.text(), "custom width"), self._parse_int(
                self.height_edit.text(), "custom height"
            )
        return R_MODE_SIZES.get(r_mode, (800, 600))

    def _shrink_to_minimal(self) -> None:
        self.adjustSize()
        hint = self.sizeHint()
        self.resize(max(560, hint.width()), hint.height())

    def _resize_to_visible_content(self) -> None:
        QTimer.singleShot(0, self._shrink_to_minimal)

    def _arrange_windows(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            self._shrink_to_minimal()
            return
        self._arrange_attempts += 1
        area = screen.availableGeometry()
        saved_bounds = self._saved_openmohaa_bounds()
        if saved_bounds:
            game_x, game_y, game_right, game_bottom = saved_bounds
            game_width = game_right - game_x
            game_height = game_bottom - game_y
        else:
            game_width, game_height = self._selected_game_size()
            game_width = min(game_width, area.width())
            game_height = min(game_height, max(240, area.height() - 120))
            game_x = area.x() + max(0, (area.width() - game_width) // 2)
            game_y = area.y()

        bounds = self.controller.move_window(game_x, game_y, game_width, game_height)
        if bounds:
            left, top, right, bottom = bounds
            actual_width = right - left
            actual_height = bottom - top
            self._capture_bounds = bounds
            self._capture_bounds_verified = True
            self.append_log(f"Positioned OpenMoHAA at {left},{top} ({actual_width}x{actual_height})")
        elif self.controller.is_running and self._arrange_attempts < 16:
            QTimer.singleShot(500, self._arrange_windows)
        elif self.controller.is_running:
            self.append_log(
                "Could not position OpenMoHAA after several attempts. "
                "On macOS this usually means Accessibility permission is missing, "
                "or OpenMoHAA's SDL window is not scriptable through System Events."
            )
        if not self._capture_bounds:
            self._capture_bounds = (game_x, game_y, game_x + game_width, game_y + game_height)
            self._capture_bounds_verified = False

        self._shrink_to_minimal()
        if not self._playback_auto_positioned:
            control_x = area.x() + max(0, (area.width() - self.width()) // 2)
            control_y = area.y() + area.height() - self.height()
            self.move(control_x, control_y)
            self._playback_auto_positioned = True

    def set_paused(self, paused: bool) -> None:
        self._sync_demo_clock()
        self._demo_paused = paused
        self.play_pause_button.setText("Play" if paused else "Pause")
        self._send(self.controller.pause if paused else lambda: self.controller.play(self._demo_speed))
        self._demo_clock_mark = time.monotonic()

    def set_speed(self, speed: float) -> None:
        self._sync_demo_clock()
        self._demo_speed = speed
        self._demo_paused = False
        if self.play_pause_button.isChecked():
            self.play_pause_button.blockSignals(True)
            self.play_pause_button.setChecked(False)
            self.play_pause_button.setText("Pause")
            self.play_pause_button.blockSignals(False)
        self._send(lambda: self.controller.set_speed(speed))
        self._demo_clock_mark = time.monotonic()

    def set_third_person(self, enabled: bool) -> None:
        self._send(lambda: self.controller.set_third_person(enabled))

    def set_scores_visible(self, visible: bool) -> None:
        self._send(self.controller.show_scores if visible else self.controller.hide_scores)

    def restart_demo(self) -> None:
        self._send(self.controller.restart_demo)
        self._reset_demo_clock()

    def stop_openmohaa(self) -> None:
        self._save_positions()
        self._send(self.controller.quit)

    def select_recording_region(self) -> None:
        if self._region_selector:
            self._region_selector.close()
        self.append_log("Select recording region: drag around the OpenMoHAA window.")
        self.video_status_label.setText("Rec: select region...")
        selector = RecordingRegionSelector()
        selector.region_selected.connect(self._set_manual_recording_region)
        selector.canceled.connect(lambda: self.append_log("Recording region selection canceled."))
        selector.canceled.connect(lambda: self.video_status_label.setText("Rec: idle"))
        selector.destroyed.connect(lambda _obj=None: setattr(self, "_region_selector", None))
        self._region_selector = selector
        selector.show()

    def _set_manual_recording_region(self, bounds: tuple[int, int, int, int]) -> None:
        self._manual_capture_bounds = bounds
        region = self._capture_region_from_bounds(bounds)
        self.video_status_label.setText(f"Region: {region.width}x{region.height}")
        self.video_status_label.setToolTip(
            f"Manual recording region: screen {region.screen_index}, {region.width}x{region.height}+{region.x},{region.y}"
        )
        self.append_log(
            "Manual recording region selected: "
            f"screen {region.screen_index}, {region.width}x{region.height}+{region.x},{region.y}"
        )

    def start_video_recording(self) -> None:
        if not self.controller.prepared:
            self._show_error("OpenMoHAA is not launched.")
            return
        video_name = sanitize_video_name(self.video_name_edit.text())
        try:
            if not self._manual_capture_bounds:
                self._refresh_openmohaa_bounds(force=True)
            region = self._recording_region()
            recording_path = self.controller.video_output_dir() / f"{video_name}.mp4"
            self.recorder.start(recording_path, region)
        except Exception as exc:  # noqa: BLE001 - GUI boundary
            self._show_recording_error(str(exc))
            self.append_log(f"ERROR: {exc}")
            return
        self._recording_path = recording_path
        self._recording_started_at = time.monotonic()
        self._recording_pending = True
        self.video_status_label.setText("Rec: starting...")
        self.video_status_label.setToolTip(str(recording_path))
        self.start_video_button.setEnabled(False)
        self.stop_video_button.setEnabled(True)
        self.append_log(
            "Recording OpenMoHAA region: "
            f"screen {region.screen_index}, {region.width}x{region.height}+{region.x},{region.y}"
        )
        self.append_log(f"Recording target: {recording_path}")

    def stop_video_recording(self) -> None:
        self.recorder.stop()
        self._recording_pending = False
        self.start_video_button.setEnabled(True)
        self.stop_video_button.setEnabled(False)
        if self._recording_path and self._recording_path.exists():
            self._show_recording_saved(self._recording_path)
        else:
            self.video_status_label.setText("Rec: stopped, no file")
            self.video_status_label.setToolTip("")

    def _reset_video_recording_status(self) -> None:
        self._recording_path = None
        self._recording_started_at = None
        self._recording_pending = False
        self.video_status_label.setText("Rec: idle")
        self.video_status_label.setToolTip("")
        self.start_video_button.setEnabled(self.controller.is_running)
        self.stop_video_button.setEnabled(False)

    def _refresh_video_recording_status(self) -> None:
        if not self._recording_pending or not self._recording_path or self._recording_started_at is None:
            return
        elapsed = max(0.0, time.monotonic() - self._recording_started_at)
        if self.recorder.process and self.recorder.process.poll() is not None:
            self._recording_pending = False
            self.start_video_button.setEnabled(self.controller.is_running)
            self.stop_video_button.setEnabled(False)
            stderr = self.recorder.stderr_text()
            if self._recording_path.exists() and self._recording_path.stat().st_size > 0:
                self._show_recording_saved(self._recording_path)
            else:
                self.video_status_label.setText("Rec: ffmpeg stopped")
                self.video_status_label.setToolTip("")
            if stderr:
                self.append_log(f"FFmpeg stopped: {stderr}")
            return
        if self._recording_path.exists():
            size = self._recording_path.stat().st_size
            self.video_status_label.setText(f"Rec: {elapsed:0.1f}s, {self._format_bytes(size)}")
            return
        if elapsed > 3.0:
            self.video_status_label.setText("Rec: waiting for file...")

    def _show_recording_saved(self, path: Path) -> None:
        size = self._format_bytes(path.stat().st_size)
        visible_path = f"{path.parent.parent.name}/{path.parent.name}/{path.name}"
        self.video_status_label.setText(f"Saved: {visible_path} ({size})")
        self.video_status_label.setToolTip(str(path))
        self.append_log(f"Video saved in: {path}")

    def approx_seek(self) -> None:
        try:
            target_seconds = self._parse_seek_seconds(self.seek_edit.text())
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self._approx_seek_to(target_seconds)

    def rewind_by(self, seconds: int) -> None:
        self._sync_demo_clock()
        self._approx_seek_to(max(0.0, self._demo_seconds - seconds))

    def _approx_seek_to(self, target_seconds: float) -> None:
        restore_speed = self._demo_speed
        restore_paused = self._demo_paused or self.play_pause_button.isChecked()
        wait_ms = int((target_seconds / self.SEEK_FAST_SPEED) * 1000)
        self._seek_generation += 1
        generation = self._seek_generation

        def start_seek() -> None:
            self.controller.restart_demo()
            self.controller.set_speed(self.SEEK_FAST_SPEED)

        if not self._send(start_seek):
            return
        self._demo_clock_active = True
        self._demo_seconds = 0.0
        self._demo_speed = self.SEEK_FAST_SPEED
        self._demo_paused = False
        self._demo_clock_mark = time.monotonic()
        self._set_status(f"Seeking {format_timestamp(target_seconds)}")
        self.seek_button.setEnabled(False)
        QTimer.singleShot(
            max(0, wait_ms),
            lambda: self._finish_approx_seek(generation, target_seconds, restore_speed, restore_paused),
        )

    def _finish_approx_seek(
        self,
        generation: int,
        target_seconds: float,
        restore_speed: float,
        restore_paused: bool,
    ) -> None:
        if generation != self._seek_generation or not self.controller.is_running:
            self.seek_button.setEnabled(self.controller.is_running)
            return

        def restore() -> None:
            if restore_paused:
                self.controller.pause()
            else:
                self.controller.play(restore_speed)

        if not self._send(restore):
            self.seek_button.setEnabled(self.controller.is_running)
            return
        self.play_pause_button.blockSignals(True)
        self.play_pause_button.setChecked(restore_paused)
        self.play_pause_button.setText("Play" if restore_paused else "Pause")
        self.play_pause_button.blockSignals(False)
        self._demo_seconds = target_seconds
        self._demo_speed = restore_speed
        self._demo_paused = restore_paused
        self._demo_clock_mark = time.monotonic()
        self._refresh_demo_timestamp()
        self.seek_button.setEnabled(True)
        self._set_status("Running")

    def _parse_seek_seconds(self, value: str) -> float:
        return parse_timestamp_seconds(value)

    def _reset_demo_clock(self) -> None:
        self._demo_seconds = 0.0
        self._demo_speed = 1.0
        self._demo_paused = False
        self._demo_clock_active = True
        self._demo_clock_mark = time.monotonic()
        self._refresh_demo_timestamp()

    def _sync_demo_clock(self) -> None:
        now = time.monotonic()
        if not self._demo_paused:
            self._demo_seconds += max(0.0, now - self._demo_clock_mark) * self._demo_speed
        self._demo_clock_mark = now

    def _refresh_demo_timestamp(self) -> None:
        self._sync_demo_clock()
        self.timestamp_label.setText(f"Est. Time: {format_timestamp(self._demo_seconds)}")

    def _format_offset_label(self, seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        return f"{minutes}m"

    def _recording_region(self) -> CaptureRegion:
        if self._manual_capture_bounds:
            return self._capture_region_from_bounds(self._manual_capture_bounds)
        if self._capture_bounds and self._capture_bounds_verified:
            return self._capture_region_from_bounds(self._capture_bounds)

        if platform.system() == "Darwin":
            raise RuntimeError(
                "Could not detect the OpenMoHAA window bounds for recording. "
                "Open the log panel for the detailed Quartz/window detection reason."
            )

        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            game_width, game_height = self._selected_game_size()
            game_width = min(game_width, area.width())
            game_height = min(game_height, max(240, area.height() - 120))
            game_x = area.x() + max(0, (area.width() - game_width) // 2)
            return CaptureRegion(game_x, area.y(), game_width, game_height)

        game_width, game_height = self._selected_game_size()
        return CaptureRegion(0, 0, game_width, game_height)

    def _capture_region_from_bounds(self, bounds: tuple[int, int, int, int]) -> CaptureRegion:
        left, top, right, bottom = bounds
        if platform.system() != "Darwin":
            return CaptureRegion(left, top, right - left, bottom - top)

        screen, screen_index = self._screen_for_bounds(bounds)
        screen = screen or self.screen() or QApplication.primaryScreen()
        if not screen:
            return CaptureRegion(left, top, right - left, bottom - top)

        geometry = screen.geometry()
        scale = screen.devicePixelRatio()
        x1 = round((left - geometry.x()) * scale)
        y1 = round((top - geometry.y()) * scale)
        x2 = round((right - geometry.x()) * scale)
        y2 = round((bottom - geometry.y()) * scale)
        x = max(0, x1)
        y = max(0, y1)
        return CaptureRegion(x, y, max(2, x2 - x), max(2, y2 - y), screen_index)

    def _screen_for_bounds(self, bounds: tuple[int, int, int, int]):
        left, top, right, bottom = bounds
        center = QPoint((left + right) // 2, (top + bottom) // 2)
        for index, screen in enumerate(QApplication.screens()):
            if screen.geometry().contains(center):
                return screen, index
        return None, 0

    def _format_bytes(self, size: int) -> str:
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
