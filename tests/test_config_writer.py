from moh_arena_demo_reviewer.config_writer import build_config_text, build_menu_text, write_review_files


def test_generated_config_contains_fallback_binds_and_canonical_freeze_cvar() -> None:
    text = build_config_text()
    assert "cl_freezeDemo" in text
    assert "cl_freezedemo" not in text
    assert 'seta cheats "1"' in text
    assert 'seta sv_cheats "1"' in text
    assert 'bind F5 "set timescale 0.0001; set cl_freezeDemo 1"' in text
    assert 'bind F10 "togglemenu moh_arena_demo_review"' in text


def test_generated_config_contains_xray_defaults_when_enabled() -> None:
    text = build_config_text(xray_enabled=True)

    assert 'seta cg_forceModel "0"' in text
    assert 'seta dm_playermodel "american_army"' in text
    assert 'seta dm_playergermanmodel "german_wehrmacht_soldier"' in text


def test_generated_menu_contains_stuffcommands() -> None:
    text = build_menu_text()
    assert 'menu "moh_arena_demo_review"' in text
    assert 'stuffcommand "set timescale 0.0001; set cl_freezeDemo 1"' in text
    assert 'stuffcommand "demo review"' in text
    assert 'stuffcommand "+scores"' in text


def test_write_review_files(tmp_path) -> None:
    config_path, autoexec_path, menu_path = write_review_files(tmp_path / "main")
    assert config_path.name == "moh_arena_demo_review.cfg"
    assert autoexec_path.name == "autoexec.cfg"
    assert menu_path.name == "moh_arena_demo_review.urc"
    assert config_path.exists()
    assert autoexec_path.exists()
    assert menu_path.exists()
