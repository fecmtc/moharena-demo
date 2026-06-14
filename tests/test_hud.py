from moh_arena_demo_reviewer.hud import (
    hide_hud_command,
    hud_update_command,
    sanitize_hud_text,
    show_hud_command,
)


def test_sanitize_hud_text_removes_console_metacharacters() -> None:
    assert sanitize_hud_text('hello"; quit\nworld') == "hello quit world"


def test_sanitize_hud_text_limits_length() -> None:
    assert sanitize_hud_text("x" * 100, max_length=12) == "x" * 12


def test_show_and_hide_hud_commands_use_hud_layer() -> None:
    assert show_hud_command() == "ui_addhud moh_arena_demo_hud_ui"
    assert hide_hud_command() == "ui_removehud moh_arena_demo_hud_ui"


def test_hud_update_command_sets_safe_lines() -> None:
    command = hud_update_command('line "1"', "line;2", "line\n3")

    assert command == (
        'set moh_arena_hud_line1 "line 1"; '
        'set moh_arena_hud_line2 "line 2"; '
        'set moh_arena_hud_line3 "line 3"'
    )
