"""Scratch-tree cleanup for the count ratchets (issue #6292).

A killed push must not leave ``merge-tree-ratchet-*`` or
``base-derived-ratchet-*`` trees in the temp dir. The subprocess tests start
the real scratch-owning code against a real repository, block it in the
counter with the scratch live, send a signal, and assert the temp dir is
empty. Each child gets its own ``TMPDIR`` so the test never sees or touches
the real ``/tmp``.
"""

from __future__ import annotations

import errno
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from scripts.ci import merge_tree_materialization as mtm

REPO_ROOT = Path(__file__).resolve().parents[2]
POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="POSIX signals and flock")
NEEDS_GIT = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
STALE = 7200

# The child publishes the live scratch path with an atomic rename, so the
# parent never reads a half-written marker.
CHILD_PRELUDE = """
import os, subprocess, sys, time
from pathlib import Path

MARKER = Path(sys.argv[1])
REPO = Path(sys.argv[2])

def announce_and_block(scratch):
    staging = MARKER.with_suffix(".tmp")
    staging.write_text(str(scratch))
    os.replace(staging, MARKER)
    time.sleep(120)
    return 0
"""

BASE_DERIVED_CHILD = """
from scripts.ci import base_derived_ratchet as brd

brd.measure_commit(REPO, "HEAD", announce_and_block)
"""

MERGE_TREE_CHILD = """
from scripts.ci import merge_tree_ratchet_check as mtrc

def rev(spec):
    return subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", spec], capture_output=True, text=True, check=True
    ).stdout.strip()

mtrc._prepare_merged_tree = lambda repo_root, base_ref: (rev("HEAD"), rev("HEAD^{tree}"), 0)
mtrc._evaluate_registered_ratchets = lambda repo_root, base_oid, scratch: announce_and_block(
    scratch
)
mtrc._evaluate_merged_tree(REPO, "origin/main")
"""


def _git(repo: Path, *argv: str) -> None:
    subprocess.run(["git", "-C", str(repo), *argv], check=True, capture_output=True)


@pytest.fixture
def small_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "count.txt").write_text("1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    return repo


def _wait_for_marker(marker: Path, proc: subprocess.Popen[bytes]) -> Path:
    deadline = time.monotonic() + 60
    while not marker.exists() and time.monotonic() < deadline and proc.poll() is None:
        time.sleep(0.05)
    assert marker.exists(), f"child never reached the counter: {proc.stderr!r}"
    return Path(marker.read_text())


def _kill_mid_run(child: str, repo: Path, temp_root: Path, sig: int) -> tuple[int, Path, str]:
    marker = temp_root.parent / "scratch-path.txt"
    env = {**os.environ, "TMPDIR": str(temp_root), "PYTHONPATH": str(REPO_ROOT)}
    proc = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(CHILD_PRELUDE + child), str(marker), str(repo)],
        cwd=REPO_ROOT,
        env=env,
        stderr=subprocess.PIPE,
    )
    try:
        scratch = _wait_for_marker(marker, proc)
        assert scratch.is_dir() and scratch.parent == temp_root
        proc.send_signal(sig)
        _, stderr = proc.communicate(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    return proc.returncode, scratch, stderr.decode()


def _aged(path: Path, seconds: float = STALE) -> Path:
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp), follow_symlinks=False)
    return path


def _stale_dir(root: Path, name: str) -> Path:
    path = root / name
    path.mkdir()
    (path / "f.txt").write_text("x")
    return _aged(path)


@POSIX_ONLY
@NEEDS_GIT
@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGHUP])
@pytest.mark.parametrize(
    "child", [BASE_DERIVED_CHILD, MERGE_TREE_CHILD], ids=["base_derived", "merge_tree"]
)
def test_signal_during_run_leaves_temp_dir_empty(
    child: str, sig: int, small_repo: Path, tmp_path: Path
) -> None:
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()

    code, scratch, _ = _kill_mid_run(child, small_repo, temp_root, sig)

    assert not scratch.exists()
    assert list(temp_root.iterdir()) == []
    assert code == 128 + sig


FAILING_REMOVAL = """
from scripts.ci import base_derived_ratchet, merge_tree_ratchet_check

def refuse(path, label):
    return f"{label} cleanup failed: PermissionError: denied"

base_derived_ratchet.remove_scratch = refuse
merge_tree_ratchet_check._remove_scratch = refuse
"""


@POSIX_ONLY
@NEEDS_GIT
@pytest.mark.parametrize(
    "child", [BASE_DERIVED_CHILD, MERGE_TREE_CHILD], ids=["base_derived", "merge_tree"]
)
def test_a_failed_removal_during_a_kill_is_reported(
    child: str, small_repo: Path, tmp_path: Path
) -> None:
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()

    code, _, stderr = _kill_mid_run(FAILING_REMOVAL + child, small_repo, temp_root, signal.SIGTERM)

    assert code == 128 + signal.SIGTERM
    assert "cleanup failed: PermissionError: denied" in stderr


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


@POSIX_ONLY
def test_second_signal_during_cleanup_does_not_abort_it() -> None:
    cleaned: list[bool] = []

    with pytest.raises(SystemExit) as info, mtm.terminate_as_exit():
        try:
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(1)
        finally:
            os.kill(os.getpid(), signal.SIGHUP)
            time.sleep(0.2)
            cleaned.append(True)

    assert cleaned == [True]
    assert info.value.code == 128 + signal.SIGTERM


def test_terminate_as_exit_is_noop_off_main_thread() -> None:
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


def test_sweep_removes_only_old_prefixed_directories(tmp_path: Path) -> None:
    old_a = _stale_dir(tmp_path, "merge-tree-ratchet-aaa")
    old_b = _stale_dir(tmp_path, "base-derived-ratchet-bbb")
    unrelated = _stale_dir(tmp_path, "pytest-of-someone")
    near_miss = _stale_dir(tmp_path, "xmerge-tree-ratchet-ccc")
    fresh = tmp_path / "merge-tree-ratchet-fresh"
    fresh.mkdir()

    removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600)

    assert removed == 2
    assert not old_a.exists() and not old_b.exists()
    assert fresh.exists() and unrelated.exists() and near_miss.exists()


def test_sweep_removes_orphaned_dotted_siblings(tmp_path: Path) -> None:
    home = _stale_dir(tmp_path, ".merge-tree-ratchet-aaa-materialize-home")
    git_home = _stale_dir(tmp_path, ".base-derived-ratchet-bbb-git-home")
    index = tmp_path / ".merge-tree-ratchet-ccc-materialize-index"
    index.write_text("x")
    _aged(index)
    foreign = _stale_dir(tmp_path, ".merge-tree-ratchet-ddd-other")

    removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600)

    assert removed == 3
    assert not home.exists() and not git_home.exists() and not index.exists()
    assert foreign.exists()


@pytest.mark.parametrize(
    ("name", "owner"),
    [
        ("merge-tree-ratchet-abc", "merge-tree-ratchet-abc"),
        (".merge-tree-ratchet-abc-git-home", "merge-tree-ratchet-abc"),
        (".base-derived-ratchet-x-materialize-index", "base-derived-ratchet-x"),
        (".merge-tree-ratchet-abc", None),
        (".pytest-abc-git-home", None),
        ("pytest-of-richard", None),
    ],
)
def test_owning_scratch_name(name: str, owner: str | None) -> None:
    assert mtm._owning_scratch_name(name, mtm.SCRATCH_PREFIXES) == owner


def test_sweep_skips_files_and_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "real-target"
    target.mkdir()
    (target / "keep.txt").write_text("x")
    link = tmp_path / "merge-tree-ratchet-link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    _aged(link)
    plain_file = tmp_path / "base-derived-ratchet-file"
    plain_file.write_text("x")
    _aged(plain_file)

    removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600)

    assert removed == 0
    assert (target / "keep.txt").exists()
    assert link.is_symlink() and plain_file.exists()


def test_stale_check_rejects_a_missing_entry(tmp_path: Path) -> None:
    assert not mtm._is_stale_and_owned(tmp_path / "gone", False, time.time())


@POSIX_ONLY
def test_sweep_skips_directories_owned_by_another_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = _stale_dir(tmp_path, "merge-tree-ratchet-other")
    monkeypatch.setattr(os, "getuid", lambda: os.stat(other).st_uid + 1)

    removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600)

    assert removed == 0
    assert other.exists()


def test_sweep_without_getuid_skips_the_ownership_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = _stale_dir(tmp_path, "merge-tree-ratchet-nouid")
    monkeypatch.delattr(os, "getuid", raising=False)

    assert mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600) == 1
    assert not stale.exists()


@POSIX_ONLY
def test_sweep_skips_a_live_scratch_tree_and_its_siblings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mtm.tempfile, "tempdir", str(tmp_path))
    live = _aged(mtm.create_scratch("merge-tree-ratchet-"))
    sibling = _stale_dir(tmp_path, f".{live.name}-git-home")

    try:
        removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600)
        assert removed == 0
        assert live.is_dir() and sibling.is_dir()
    finally:
        assert mtm.remove_scratch(live, "test scratch") is None

    assert not live.exists()
    assert mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600) == 1
    assert not sibling.exists()


def test_create_scratch_skips_the_lock_where_the_filesystem_has_no_flock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(_path: Path, _operation: int) -> int:
        raise OSError(errno.ENOLCK, "no locks here")

    monkeypatch.setattr(mtm.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(mtm.sys, "platform", "linux")
    monkeypatch.setattr(mtm, "_open_locked", refuse)

    scratch = mtm.create_scratch("base-derived-ratchet-")

    assert scratch.is_dir() and scratch not in mtm._HELD_SCRATCH_LOCKS
    assert "scratch lock skipped" in capsys.readouterr().err
    assert mtm.remove_scratch(scratch, "test scratch") is None
    assert not scratch.exists()


@pytest.mark.parametrize("code", [errno.EMFILE, errno.EACCES, None])
def test_create_scratch_aborts_and_removes_the_tree_when_the_lock_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int | None
) -> None:
    """A tree with no lock is sweepable once it passes the age floor."""

    def refuse(_path: Path, _operation: int) -> int:
        raise OSError(code, "lock failed") if code is not None else OSError("lock failed")

    monkeypatch.setattr(mtm.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(mtm.sys, "platform", "linux")
    monkeypatch.setattr(mtm, "_open_locked", refuse)

    with pytest.raises(OSError, match="lock failed"):
        mtm.create_scratch("base-derived-ratchet-")

    assert list(tmp_path.iterdir()) == []
    # The registry is process-global and other tests on this worker may leave
    # entries, so check only the keys this test could have created.
    assert not any(held.parent == tmp_path for held in mtm._HELD_SCRATCH_LOCKS)


@POSIX_ONLY
def test_planted_foreign_lock_does_not_block_cleanup_of_our_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another user plants the owner directory and holds its lock in a shared temp dir."""
    planted = tmp_path / "merge-tree-ratchet-abc"
    planted.mkdir()
    sibling = _stale_dir(tmp_path, ".merge-tree-ratchet-abc-git-home")
    real_uid = os.getuid()
    holder = mtm._open_locked(planted, mtm.fcntl.LOCK_EX)
    try:
        monkeypatch.setattr(os, "getuid", lambda: real_uid)
        monkeypatch.setattr(mtm, "_owned_by_current_user", lambda _path: False)

        removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600)
    finally:
        os.close(holder)

    assert removed == 1
    assert not sibling.exists()


@POSIX_ONLY
def test_our_own_locked_owner_still_protects_its_sibling(tmp_path: Path) -> None:
    owner = tmp_path / "merge-tree-ratchet-abc"
    owner.mkdir()
    sibling = _stale_dir(tmp_path, ".merge-tree-ratchet-abc-git-home")
    holder = mtm._open_locked(owner, mtm.fcntl.LOCK_SH)
    try:
        removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600)
    finally:
        os.close(holder)

    assert removed == 0
    assert sibling.exists()


def test_owned_by_current_user_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    here = tmp_path / "here"
    here.mkdir()
    assert mtm._owned_by_current_user(here)
    assert mtm._owned_by_current_user(tmp_path / "missing")
    if hasattr(os, "getuid"):
        monkeypatch.setattr(os, "getuid", lambda: here.lstat().st_uid + 1)
        assert not mtm._owned_by_current_user(here)
        monkeypatch.delattr(os, "getuid")
    assert mtm._owned_by_current_user(here)


def test_without_flock_the_age_floor_alone_decides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mtm.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(mtm.sys, "platform", "win32")
    scratch = _aged(mtm.create_scratch("merge-tree-ratchet-"))

    assert scratch not in mtm._HELD_SCRATCH_LOCKS
    assert mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600) == 1
    assert not scratch.exists()


def test_sweep_reports_unreadable_temp_root_without_raising(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    removed = mtm.sweep_stale_scratch(temp_root=tmp_path / "missing")

    assert removed == 0
    assert "scratch sweep skipped" in capsys.readouterr().err


def test_sweep_reports_failed_removal_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stuck = _stale_dir(tmp_path, "merge-tree-ratchet-stuck")
    other = _stale_dir(tmp_path, "base-derived-ratchet-other")
    real_remove_tree = mtm.remove_tree

    def fail_on_stuck(path: Path, label: str) -> str | None:
        if path == stuck:
            return f"{label} cleanup failed: boom"
        return real_remove_tree(path, label)

    monkeypatch.setattr(mtm, "remove_tree", fail_on_stuck)

    removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600)

    assert removed == 1
    assert stuck.exists() and not other.exists()
    assert "cleanup failed: boom" in capsys.readouterr().err


def test_sweep_reports_a_sibling_file_it_cannot_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    index = tmp_path / ".merge-tree-ratchet-x-materialize-index"
    index.write_text("x")
    _aged(index)

    def refuse(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "unlink", refuse)

    removed = mtm.sweep_stale_scratch(temp_root=tmp_path, max_age_seconds=3600)

    assert removed == 0
    assert "PermissionError: denied" in capsys.readouterr().err


def test_guarded_scratch_sweeps_before_running_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = _stale_dir(tmp_path, "base-derived-ratchet-old")
    monkeypatch.setattr(mtm.tempfile, "gettempdir", lambda: str(tmp_path))

    with mtm.guarded_scratch():
        assert not stale.exists()
