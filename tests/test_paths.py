import os
import stat

import pytest

from moh_arena_demo_reviewer.paths import (
    PipeNotFifoError,
    PipeTimeoutError,
    expected_pipe_path,
    find_pipe,
    prepare_homepath,
)


def test_prepare_homepath_copies_demo_as_review_dm8(tmp_path) -> None:
    demo = tmp_path / "sample.dm_8"
    demo.write_bytes(b"demo-data")

    prepared = prepare_homepath(demo, tmp_path)

    assert prepared.homepath.parent == tmp_path
    assert prepared.demo_path == prepared.homepath / "main" / "demos" / "review.dm_8"
    assert prepared.demo_path.read_bytes() == b"demo-data"
    assert prepared.config_path.exists()
    assert prepared.autoexec_path.exists()
    assert prepared.menu_path.exists()
    assert prepared.screenshots_dir.exists()
    assert prepared.videos_dir.exists()


def test_prepare_homepath_renames_demo_aa_input(tmp_path) -> None:
    demo = tmp_path / "match.demo_aa"
    demo.write_bytes(b"demo-aa-data")

    prepared = prepare_homepath(demo, tmp_path)

    assert prepared.demo_path.name == "review.dm_8"
    assert prepared.demo_path.read_bytes() == b"demo-aa-data"


def test_prepare_homepath_copies_xray_pk3_when_enabled(tmp_path) -> None:
    demo = tmp_path / "sample.dm_8"
    demo.write_bytes(b"demo-data")
    xray = tmp_path / "zzz-Dark_Sniper_zztoggleskin_fix.pk3"
    xray.write_bytes(b"pk3-data")

    prepared = prepare_homepath(demo, tmp_path, xray_enabled=True, xray_source=xray)

    assert prepared.xray_pk3_path == prepared.main_dir / "zzz-Dark_Sniper_zztoggleskin_fix.pk3"
    assert prepared.xray_pk3_path.read_bytes() == b"pk3-data"


def test_prepare_homepath_skips_xray_pk3_by_default(tmp_path) -> None:
    demo = tmp_path / "sample.dm_8"
    demo.write_bytes(b"demo-data")

    prepared = prepare_homepath(demo, tmp_path)

    assert prepared.xray_pk3_path is None
    assert not (prepared.main_dir / "zzz-Dark_Sniper_zztoggleskin_fix.pk3").exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO requires POSIX")
def test_find_pipe_detects_fifo(tmp_path) -> None:
    pipe_path = expected_pipe_path(tmp_path)
    pipe_path.parent.mkdir(parents=True)
    os.mkfifo(pipe_path)

    found = find_pipe(tmp_path, timeout=0.1, poll_interval=0.01)

    assert found == pipe_path
    assert stat.S_ISFIFO(os.stat(found).st_mode)


def test_find_pipe_times_out(tmp_path) -> None:
    with pytest.raises(PipeTimeoutError):
        find_pipe(tmp_path, timeout=0.01, poll_interval=0.001)


def test_find_pipe_rejects_non_fifo(tmp_path) -> None:
    pipe_path = expected_pipe_path(tmp_path)
    pipe_path.parent.mkdir(parents=True)
    pipe_path.write_text("not a pipe")

    with pytest.raises(PipeNotFifoError):
        find_pipe(tmp_path, timeout=0.1, poll_interval=0.01)
