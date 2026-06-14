"""Copy the committed OpenMoHAA review game files into a launch homepath.

The launch assets (config, autoexec, and the in-game ``.urc`` menus) are now
checked-in, hand-editable game files under :data:`GAME_FILES_DIR`. They used to
be generated on the fly; they are plain game files, so we commit them and copy
them verbatim into each review homepath instead.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .commands import CONFIG_NAME, MENU_NAME
from .hud import HUD_UI_MENU

GAME_FILES_DIR = Path(__file__).resolve().parent / "game_files"

AUTOEXEC_NAME = "autoexec.cfg"
MENU_FILE = f"{MENU_NAME}.urc"
HUD_UI_FILE = f"{HUD_UI_MENU}.urc"


def write_review_files(main_dir: Path) -> tuple[Path, Path, Path, Path]:
    """Copy the committed game files into ``main_dir``.

    Returns ``(config_path, autoexec_path, menu_path, hud_ui_path)``.
    """
    main_dir = Path(main_dir)
    ui_dir = main_dir / "ui"
    main_dir.mkdir(parents=True, exist_ok=True)
    ui_dir.mkdir(parents=True, exist_ok=True)

    config_path = main_dir / CONFIG_NAME
    autoexec_path = main_dir / AUTOEXEC_NAME
    menu_path = ui_dir / MENU_FILE
    hud_ui_path = ui_dir / HUD_UI_FILE

    shutil.copyfile(GAME_FILES_DIR / CONFIG_NAME, config_path)
    shutil.copyfile(GAME_FILES_DIR / AUTOEXEC_NAME, autoexec_path)
    shutil.copyfile(GAME_FILES_DIR / "ui" / MENU_FILE, menu_path)
    shutil.copyfile(GAME_FILES_DIR / "ui" / HUD_UI_FILE, hud_ui_path)

    return config_path, autoexec_path, menu_path, hud_ui_path
