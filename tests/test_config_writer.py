from pathlib import Path

from moh_arena_demo_reviewer.commands import CONFIG_NAME
from moh_arena_demo_reviewer.config_writer import (
    AUTOEXEC_NAME,
    GAME_FILES_DIR,
    HUD_UI_FILE,
    MENU_FILE,
    write_review_files,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_committed_game_files_exist() -> None:
    assert (GAME_FILES_DIR / CONFIG_NAME).is_file()
    assert (GAME_FILES_DIR / AUTOEXEC_NAME).is_file()
    assert (GAME_FILES_DIR / "ui" / MENU_FILE).is_file()
    assert (GAME_FILES_DIR / "ui" / HUD_UI_FILE).is_file()


def test_config_has_cvars_and_fallback_binds() -> None:
    text = _read(GAME_FILES_DIR / CONFIG_NAME)
    assert "cl_freezeDemo" in text
    assert "cl_freezedemo" not in text
    assert 'seta cheats "1"' in text
    assert 'seta sv_cheats "1"' in text
    assert 'seta logfile "2"' in text
    assert 'seta logfile_timestamps "1"' in text
    assert 'seta fps "0"' in text
    assert 'seta ui_weaponsbar "0"' in text
    assert "seta moh_arena_hud_line1" in text
    assert 'bind F5 "set timescale 0.0001; set cl_freezeDemo 1"' in text
    assert 'bind F10 "togglemenu moh_arena_demo_review"' in text
    assert 'bind F9 "+scores"' in text
    assert 'bind F11 "-scores"' in text
    assert 'bind F12 "screenshot"' in text
    # x-ray defaults are launch args now, not baked into the committed config.
    assert "cg_forceModel" not in text
    # runtime menu (re)loading crashes UI_Update; never in the boot config.
    assert "loadmenu" not in text


def test_menu_has_controls_and_hud_toggle() -> None:
    text = _read(GAME_FILES_DIR / "ui" / MENU_FILE)
    assert 'menu "moh_arena_demo_review"' in text
    assert 'title "MoH Arena Demo Review"' in text
    assert 'stuffcommand "set timescale 0.0001; set cl_freezeDemo 1"' in text
    assert 'stuffcommand "demo review"' in text
    # Scores + must close this menu first, or the engine force-hides the
    # scoreboard while a UI menu is active (UI_ShowScoreboard_f / UI_MenuActive).
    assert 'stuffcommand "togglemenu moh_arena_demo_review; +scores"' in text
    assert 'stuffcommand "-scores"' in text
    assert 'stuffcommand "set timescale 16; set cl_freezeDemo 0"' in text
    assert 'stuffcommand "set timescale 64; set cl_freezeDemo 0"' in text
    assert 'stuffcommand "toggle cg_3rd_person"' in text
    assert 'stuffcommand "quit"' in text
    assert 'stuffcommand "ui_addhud moh_arena_demo_hud_ui"' in text
    assert 'stuffcommand "ui_removehud moh_arena_demo_hud_ui"' in text
    assert 'title "PLAYBACK"' in text
    assert 'title "SPEED"' in text
    assert 'title "VIEW"' in text
    assert "loadmenu" not in text


def test_hud_ui_uses_linkcvar_labels() -> None:
    text = _read(GAME_FILES_DIR / "ui" / HUD_UI_FILE)
    assert 'menu "moh_arena_demo_hud_ui"' in text
    assert 'name "moh_arena_hud_ui_line1"' in text
    assert 'linkcvar "moh_arena_hud_line1"' in text
    assert 'linkcvar "moh_arena_hud_line2"' in text
    assert 'linkcvar "moh_arena_hud_line3"' in text
    # the .scr huddraw path is gone; the overlay is pure client UI.
    assert "huddraw_" not in text


def test_write_review_files_copies_assets_into_homepath(tmp_path) -> None:
    main_dir = tmp_path / "main"
    config_path, autoexec_path, menu_path, hud_ui_path = write_review_files(main_dir)

    assert config_path == main_dir / CONFIG_NAME
    assert autoexec_path == main_dir / AUTOEXEC_NAME
    assert menu_path == main_dir / "ui" / MENU_FILE
    assert hud_ui_path == main_dir / "ui" / HUD_UI_FILE
    for path in (config_path, autoexec_path, menu_path, hud_ui_path):
        assert path.is_file()

    # copied verbatim from the committed source
    assert menu_path.read_text(encoding="utf-8") == (GAME_FILES_DIR / "ui" / MENU_FILE).read_text(encoding="utf-8")
    # the dead server-script HUD hooks are gone
    assert not (main_dir / "global").exists()
