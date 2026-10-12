"""Scratch-tree cleanup for the count ratchets (issue #6292).

A killed push must not leave ``merge-tree-ratchet-*`` or
``base-derived-ratchet-*`` trees in the temp dir. The subprocess tests start
the real scratch-owning code, block it mid-run with the scratch live, send a
signal, and assert the tree is gone. Each child gets its own ``TMPDIR`` so the
test never sees or touches the real ``/tmp``.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from scripts.ci import merge_tree_materialization as mtm

REPO_ROOT = Path(__file__).resolve().parents[2]
POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="POSIX signals")

BASE_DERIVED_CHILD = """
import sys, time
from pathlib import Path
from scripts.ci import base_derived_ratchet as brd

def counter(scratch):
    Path(sys.argv[1]).write_text(str(scratch))
    time.sleep(120)
    return 0

brd.CommitScratch._materialize = lambda self: setattr(
    self, "_scratch", Path(__import__("tempfile").mkdtemp(prefix="base-derived-ratchet-"))
) or True
brd.measure_commit(Path("."), "HEAD", counter)
"""

MERGE_TREE_CHILD = """
import sys, time
from pathlib import Path
from scripts.ci import merge_tree_ratchet_check as mtrc

mtrc._materialize_tree = lambda *a, **k: True
mtrc._init_scratch_repo = lambda *a, **k: True

def block(repo_root, base_oid, scratch_root):
    Path(sys.argv[1]).write_text(str(scratch_root))
    time.sleep(120)
    return 0

mtrc._evaluate_registered_ratchets = block
mtrc._prepare_merged_tree = lambda repo_root, base_ref: ("base", "tree", 0)
mtrc._evaluate_merged_tree(Path("."), "origin/main")
"""


def _run_until_scratch_exists(child_code: str, tmp_path: Path, sig: int) -> tuple[int, Path]:
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    marker = tmp_path / "scratch-path.txt"
    env = {**os.environ, "TMPDIR": str(temp_root), "PYTHONPATH": str(REPO_ROOT)}
    proc = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(child_code), str(marker)],
        cwd=REPO_ROOT,
        env=env,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 30
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert marker.exists(), "child never created its scratch dir"
    scratch = Path(marker.read_text())
    assert scratch.is_dir()
    proc.send_signal(sig)
    proc.wait(timeout=30)
    return proc.returncode, scratch


@POSIX_ONLY
@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP])
@pytest.mark.parametrize(
    "child", [BASE_DERIVED_CHILD, MERGE_TREE_CHILD], ids=["base_derived", "merge_tree"]
)
def test_signal_during_run_removes_scratch(child: str, sig: int, tmp_path: Path) -> None:
    code, scratch = _run_until_scratch_exists(child, tmp_path, sig)

    assert not scratch.exists()
    assert code == 128 + sig


@POSIX_ONLY
def test_terminate_as_exit_restores_previous_handlers() -> None:
    before = signal.getsignal(signal.SIGTERM)

    with mtm.terminate_as_exit():
        assert signal.getsignal(signal.SIGTERM) is not before

    assert signal.getsignal(signal.SIGTERM) == before


@POSIX_ONLY
def test_terminate_as_exit_raises_system_exit_on_sigterm() -> None:
    with pytest.raises(SystemExit) as info, mtm.terminate_as_exit():
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(1)

    assert info.value.code == 128 + signal.SIGTERM


def test_terminate_as_exit_is_noop_off_main_thread() -> None:
    import threading

    errors: list[BaseException] = []

    def body() -> None:
        try:
            with mtm.terminate_as_exit():
                pass
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=body)
    thread.start()
    thread.join()

    assert errors == []


def _aged(path: Path, seconds: float) -> None:
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


def test_sweep_removes_only_old_prefixed_directories(tmp_path: Path) -> None:
    old_a = tmp_path / "merge-tree-ratchet-aaa"
    old_b = tmp_path / "base-derived-ratchet-bbb"
    fresh = tmp_path / "merge-tree-ratchet-fresh"
    unrelated = tmp_path / "pytest-of-someone"
    near_miss = tmp_path / "xmerge-tree-ratchet-ccc"
    for d in (old_a, old_b, fresh, unrelated, near_miss):
        d.mkdir()
        (d / "f.txt").write_text("x")
    for d in (old_a, old_b, unrelated, near_miss):
        _aged(d, 7200)

    removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600)

    assert removed == 2
    assert not old_a.exists() and not old_b.exists()
    assert fresh.exists() and unrelated.exists() and near_miss.exists()


def test_sweep_skips_files_and_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "real-target"
    target.mkdir()
    (target / "keep.txt").write_text("x")
    link = tmp_path / "merge-tree-ratchet-link"
    link.symlink_to(target, target_is_directory=True)
    plain_file = tmp_path / "base-derived-ratchet-file"
    plain_file.write_text("x")
    _aged(plain_file, 7200)

    removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=0)

    assert removed == 0
    assert (target / "keep.txt").exists()
    assert link.is_symlink() and plain_file.exists()


@POSIX_ONLY
def test_sweep_skips_directories_owned_by_another_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path / "merge-tree-ratchet-other"
    other.mkdir()
    _aged(other, 7200)
    monkeypatch.setattr(os, "getuid", lambda: os.stat(other).st_uid + 1)

    removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600)

    assert removed == 0
    assert other.exists()


def test_sweep_reports_unreadable_temp_root_without_raising(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    removed = mtm.sweep_stale_scratch(temp_root=tmp_path / "missing")

    assert removed == 0
    assert "scratch sweep skipped" in capsys.readouterr().err


def test_sweep_reports_failed_removal_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stuck = tmp_path / "merge-tree-ratchet-stuck"
    stuck.mkdir()
    _aged(stuck, 7200)
    monkeypatch.setattr(mtm, "remove_tree", lambda path, label: f"{label} cleanup failed: boom")

    removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600)

    assert removed == 0
    assert "cleanup failed: boom" in capsys.readouterr().err


def test_guarded_scratch_sweeps_before_running_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = tmp_path / "base-derived-ratchet-old"
    stale.mkdir()
    _aged(stale, 7200)
    monkeypatch.setattr(mtm.tempfile, "gettempdir", lambda: str(tmp_path))

    with mtm.guarded_scratch():
        assert not stale.exists()
