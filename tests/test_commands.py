import pytest

from moh_arena_demo_reviewer import commands


def test_command_strings_use_canonical_cvars() -> None:
    assert commands.pause_command() == "set timescale 0.0001; set cl_freezeDemo 1"
    assert commands.play_command() == "set timescale 1; set cl_freezeDemo 0"
    assert commands.set_speed_command(0.25) == "set timescale 0.25; set cl_freezeDemo 0"
    assert commands.toggle_third_person_command() == "toggle cg_3rd_person"
    assert commands.set_third_person_command(True) == "set cg_3rd_person 1"
    assert commands.set_third_person_command(False) == "set cg_3rd_person 0"
    assert commands.show_scores_command() == "+scores"
    assert commands.hide_scores_command() == "-scores"
    assert commands.restart_demo_command() == "demo review"
    assert commands.screenshot_command() == "screenshot"
    assert commands.start_video_command("clip 1") == "video clip_1"
    assert commands.stop_video_command() == "stopvideo"
    assert commands.quit_command() == "quit"


def test_speed_must_be_positive() -> None:
    with pytest.raises(ValueError):
        commands.play_command(0)


def test_parse_timestamp_seconds_accepts_review_formats() -> None:
    assert commands.parse_timestamp_seconds("90") == 90
    assert commands.parse_timestamp_seconds("02:30") == 150
    assert commands.parse_timestamp_seconds("1:02:03.5") == 3723.5


def test_parse_timestamp_seconds_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        commands.parse_timestamp_seconds("")
    with pytest.raises(ValueError):
        commands.parse_timestamp_seconds("-1")
    with pytest.raises(ValueError):
        commands.parse_timestamp_seconds("1:2:3:4")


def test_format_timestamp() -> None:
    assert commands.format_timestamp(9.25) == "00:09.2"
    assert commands.format_timestamp(150) == "02:30.0"
    assert commands.format_timestamp(3723.5) == "1:02:03.5"
