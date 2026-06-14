"""Helpers for driving the in-game review HUD overlay through cvars.

The HUD is a client UI menu (``moh_arena_demo_hud_ui.urc``) whose Labels are
``linkcvar``-bound to the cvars below, so updating the text is just ``set``-ing
those cvars over ``com_pipefile``. Visibility is toggled with ``ui_addhud`` /
``ui_removehud`` (the no-focus HUD layer) -- never ``loadmenu`` at runtime, which
rebuilds the menu system and crashes ``UI_Update``. ``showmenu`` / ``hidemenu``
are a menu-layer fallback if a particular build misbehaves.
"""

from __future__ import annotations

import re

HUD_LINE_CVARS = ("moh_arena_hud_line1", "moh_arena_hud_line2", "moh_arena_hud_line3")
HUD_UI_MENU = "moh_arena_demo_hud_ui"
HUD_MAX_LINE_LENGTH = 72


def sanitize_hud_text(text: str, max_length: int = HUD_MAX_LINE_LENGTH) -> str:
    cleaned = re.sub(r'[";\r\n]+', " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_length]


def show_hud_command() -> str:
    return f"ui_addhud {HUD_UI_MENU}"


def hide_hud_command() -> str:
    return f"ui_removehud {HUD_UI_MENU}"


def hud_update_command(line1: str, line2: str = "", line3: str = "") -> str:
    commands = []
    for cvar, value in zip(HUD_LINE_CVARS, (line1, line2, line3)):
        commands.append(f'set {cvar} "{sanitize_hud_text(value)}"')
    return "; ".join(commands)
