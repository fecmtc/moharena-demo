from pathlib import Path

from moh_arena_demo_reviewer.openmohaa_controller import (
    OpenMohaaController,
    _bounds_from_quartz_windows,
    build_openmohaa_argv,
    infer_basepath_from_executable,
    strip_terminal_controls,
)
from moh_arena_demo_reviewer.paths import PreparedHomepath


def test_build_openmohaa_argv_preserves_paths_with_spaces() -> None:
    argv = build_openmohaa_argv(
        Path("/Applications/Open MoHAA/openmohaa"),
        Path("/Games/MOHAA Assets"),
        Path("/tmp/moh arena review/home"),
    )

    assert argv[0] == "/Applications/Open MoHAA/openmohaa"
    assert argv[1:7] == [
        "+set",
        "fs_basepath",
        "/Games/MOHAA Assets",
        "+set",
        "fs_homepath",
        "/tmp/moh arena review/home",
    ]
    assert argv[-4:] == ["+exec", "moh_arena_demo_review.cfg", "+demo", "review"]
    assert argv[argv.index("r_mode") + 1] == "-1"
    assert argv[argv.index("cheats") + 1] == "1"
    assert argv[argv.index("sv_cheats") + 1] == "1"
    assert argv[argv.index("logfile") + 1] == "2"
    assert argv[argv.index("logfile_timestamps") + 1] == "1"
    assert argv[argv.index("fps") + 1] == "0"
    assert "cl_freezeDemo" in argv
    assert "moh_arena_pipe" in argv


def test_build_openmohaa_argv_accepts_specific_r_mode() -> None:
    argv = build_openmohaa_argv("openmohaa", "/games/mohaa", "/tmp/review", r_mode=4)

    assert argv[argv.index("r_mode") + 1] == "4"


def test_build_openmohaa_argv_omits_xray_cvars_by_default() -> None:
    argv = build_openmohaa_argv("openmohaa", "/games/mohaa", "/tmp/review")

    assert "cg_forceModel" not in argv
    assert "dm_playermodel" not in argv


def test_build_openmohaa_argv_injects_xray_cvars_before_exec() -> None:
    argv = build_openmohaa_argv("openmohaa", "/games/mohaa", "/tmp/review", xray_enabled=True)

    assert argv[argv.index("cg_forceModel") + 1] == "0"
    assert argv[argv.index("dm_playermodel") + 1] == "american_army"
    assert argv[argv.index("dm_playergermanmodel") + 1] == "german_wehrmacht_soldier"
    # x-ray sets come before the trailing exec/demo tail
    assert argv.index("dm_playergermanmodel") < argv.index("+exec")
    assert argv[-4:] == ["+exec", "moh_arena_demo_review.cfg", "+demo", "review"]


def test_infer_basepath_from_executable_uses_executable_parent() -> None:
    assert infer_basepath_from_executable("/Users/me/openmohaa/openmohaa") == Path("/Users/me/openmohaa")


def test_infer_basepath_from_macos_app_bundle_uses_bundle_parent() -> None:
    executable = "/Applications/OpenMoHAA.app/Contents/MacOS/openmohaa"

    assert infer_basepath_from_executable(executable) == Path("/Applications")


def test_strip_terminal_controls_removes_backspace_and_ansi_noise() -> None:
    assert strip_terminal_controls("tty]\b \b\b \bhello\x1b[0m") == "tty]hello"


def test_cleanup_xray_pk3_removes_copied_file(tmp_path) -> None:
    xray = tmp_path / "main" / "zzz-Dark_Sniper_zztoggleskin_fix.pk3"
    xray.parent.mkdir()
    xray.write_bytes(b"pk3-data")
    controller = OpenMohaaController()
    controller.prepared = PreparedHomepath(
        homepath=tmp_path,
        main_dir=tmp_path / "main",
        demos_dir=tmp_path / "main" / "demos",
        demo_path=tmp_path / "main" / "demos" / "review.dm_8",
        config_path=tmp_path / "main" / "moh_arena_demo_review.cfg",
        autoexec_path=tmp_path / "main" / "autoexec.cfg",
        menu_path=tmp_path / "main" / "ui" / "moh_arena_demo_review.urc",
        hud_ui_path=tmp_path / "main" / "ui" / "moh_arena_demo_hud_ui.urc",
        qconsole_log_path=tmp_path / "main" / "qconsole.log",
        pipe_path=tmp_path / "main" / "moh_arena_pipe",
        screenshots_dir=tmp_path / "main" / "screenshots",
        videos_dir=tmp_path / "main" / "videos",
        xray_pk3_path=xray,
    )

    controller.cleanup_xray_pk3()
    controller.cleanup_xray_pk3()

    assert not xray.exists()


def test_python_qconsole_tee_writes_to_prepared_homepath(tmp_path) -> None:
    controller = OpenMohaaController()
    controller.prepared = PreparedHomepath(
        homepath=tmp_path,
        main_dir=tmp_path / "main",
        demos_dir=tmp_path / "main" / "demos",
        demo_path=tmp_path / "main" / "demos" / "review.dm_8",
        config_path=tmp_path / "main" / "moh_arena_demo_review.cfg",
        autoexec_path=tmp_path / "main" / "autoexec.cfg",
        menu_path=tmp_path / "main" / "ui" / "moh_arena_demo_review.urc",
        hud_ui_path=tmp_path / "main" / "ui" / "moh_arena_demo_hud_ui.urc",
        qconsole_log_path=tmp_path / "main" / "qconsole.log",
        pipe_path=tmp_path / "main" / "moh_arena_pipe",
        screenshots_dir=tmp_path / "main" / "screenshots",
        videos_dir=tmp_path / "main" / "videos",
    )

    controller._append_qconsole("hello qconsole")  # noqa: SLF001 - verifies the tee helper directly

    assert (tmp_path / "main" / "qconsole.log").read_text(encoding="utf-8") == "hello qconsole\n"


def test_remove_stale_xray_pk3_deletes_known_artifact_from_basepath(tmp_path) -> None:
    from moh_arena_demo_reviewer.paths import default_xray_pk3_path

    basepath = tmp_path / "OpenMoHAA"
    main_dir = basepath / "main"
    main_dir.mkdir(parents=True)
    stale = main_dir / default_xray_pk3_path().name
    stale.write_bytes(b"pk3")
    unrelated = main_dir / "some_other.pk3"
    unrelated.write_bytes(b"keep")

    controller = OpenMohaaController()
    controller._remove_stale_xray_pk3(basepath)  # noqa: SLF001 - exercises the helper directly

    assert not stale.exists()
    assert unrelated.exists()


def test_remove_stale_xray_pk3_noop_when_absent(tmp_path) -> None:
    basepath = tmp_path / "OpenMoHAA"
    (basepath / "main").mkdir(parents=True)

    controller = OpenMohaaController()
    controller._remove_stale_xray_pk3(basepath)  # noqa: SLF001 - must not raise when nothing to remove


def test_video_output_dir_uses_basepath_main_videos(tmp_path) -> None:
    controller = OpenMohaaController()
    controller.basepath = tmp_path / "OpenMoHAA"

    videos_dir = controller.video_output_dir()

    assert videos_dir == tmp_path / "OpenMoHAA" / "main" / "videos"
    assert videos_dir.exists()


def test_bounds_from_quartz_windows_picks_largest_onscreen_pid_window() -> None:
    windows = [
        {
            "kCGWindowOwnerPID": 99,
            "kCGWindowLayer": 0,
            "kCGWindowIsOnscreen": True,
            "kCGWindowAlpha": 1,
            "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 1920, "Height": 1080},
        },
        {
            "kCGWindowOwnerPID": 123,
            "kCGWindowLayer": 0,
            "kCGWindowIsOnscreen": True,
            "kCGWindowAlpha": 1,
            "kCGWindowBounds": {"X": 50, "Y": 60, "Width": 100, "Height": 100},
        },
        {
            "kCGWindowOwnerPID": 123,
            "kCGWindowLayer": 0,
            "kCGWindowIsOnscreen": True,
            "kCGWindowAlpha": 1,
            "kCGWindowBounds": {"X": 200, "Y": 100, "Width": 1280, "Height": 720},
        },
    ]

    assert _bounds_from_quartz_windows(windows, 123) == (200, 100, 1480, 820)


def test_bounds_from_quartz_windows_matches_pid_set() -> None:
    windows = [
        {
            "kCGWindowOwnerPID": 456,
            "kCGWindowLayer": 0,
            "kCGWindowIsOnscreen": True,
            "kCGWindowAlpha": 1,
            "kCGWindowBounds": {"X": 20, "Y": 30, "Width": 640, "Height": 480},
        },
    ]

    assert _bounds_from_quartz_windows(windows, {123, 456}) == (20, 30, 660, 510)


def test_bounds_from_quartz_windows_matches_owner_name_fragment() -> None:
    windows = [
        {
            "kCGWindowOwnerPID": 999,
            "kCGWindowOwnerName": "OpenMoHAA",
            "kCGWindowLayer": 0,
            "kCGWindowIsOnscreen": True,
            "kCGWindowAlpha": 1,
            "kCGWindowBounds": {"X": 5, "Y": 6, "Width": 800, "Height": 600},
        },
    ]

    assert _bounds_from_quartz_windows(windows, {123}, ("openmohaa",)) == (5, 6, 805, 606)


def test_bounds_from_quartz_windows_ignores_non_normal_windows() -> None:
    windows = [
        {
            "kCGWindowOwnerPID": 123,
            "kCGWindowLayer": 25,
            "kCGWindowIsOnscreen": True,
            "kCGWindowAlpha": 1,
            "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 1280, "Height": 720},
        },
        {
            "kCGWindowOwnerPID": 123,
            "kCGWindowLayer": 0,
            "kCGWindowIsOnscreen": False,
            "kCGWindowAlpha": 1,
            "kCGWindowBounds": {"X": 10, "Y": 10, "Width": 1280, "Height": 720},
        },
    ]

    assert _bounds_from_quartz_windows(windows, 123) is None
