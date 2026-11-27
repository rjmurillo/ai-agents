"""Tests for scripts/eval/_controller_lock.py, the one-controller locks.

Marked `windows_path`, so the Windows job runs the real `msvcrt` branch. On
POSIX the same tests run the `fcntl` branch. A second open file description
contends with the first even inside one process, under `flock` and under
`msvcrt.locking`, so contention needs no second process here.
"""

from __future__ import annotations

import errno
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

_EVAL = Path(__file__).resolve().parents[2] / "scripts" / "eval"
sys.path.insert(0, str(_EVAL))

import _controller_lock as lock  # noqa: E402
from _controller_config import ControllerError  # noqa: E402

pytestmark = pytest.mark.windows_path


def test_second_holder_is_refused_with_the_busy_message(tmp_path: Path) -> None:
    path = tmp_path / "x.lock"
    with lock.exclusive(path, "first"):
        with pytest.raises(ControllerError, match="^second$"):
            with lock.exclusive(path, "second"):
                pass
        # The refused attempt did not remove the holder's file.
        assert path.exists()


def test_release_keeps_the_file_and_frees_the_lock(tmp_path: Path) -> None:
    path = tmp_path / "x.lock"
    with lock.exclusive(path, "busy"):
        assert path.exists()
    assert path.is_file()
    with lock.exclusive(path, "busy"):
        pass


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_release_never_follows_a_link_swapped_in_while_held(tmp_path: Path) -> None:
    # A child swaps the lock path for a link to a file it wants removed.
    victim = tmp_path / "victim"
    victim.write_text("keep", encoding="utf-8")
    path = tmp_path / "x.lock"
    with lock.exclusive(path, "busy"):
        os.unlink(path)
        path.symlink_to(victim)
    assert victim.read_text(encoding="utf-8") == "keep"
    assert path.is_symlink()


def test_release_runs_when_the_body_raises(tmp_path: Path) -> None:
    path = tmp_path / "x.lock"
    with pytest.raises(RuntimeError):
        with lock.exclusive(path, "busy"):
            raise RuntimeError("boom")
    with lock.exclusive(path, "busy"):
        pass


def test_a_leftover_unlocked_file_does_not_block(tmp_path: Path) -> None:
    # What a crash leaves: the file, with no process holding a lock on it.
    path = tmp_path / "x.lock"
    path.write_bytes(b"")
    with lock.exclusive(path, "busy"):
        pass


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_a_link_planted_at_the_lock_path_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("keep", encoding="utf-8")
    path = tmp_path / "x.lock"
    path.symlink_to(target)
    with pytest.raises(ControllerError, match="could not open lock file"):
        with lock.exclusive(path, "busy"):
            pass
    assert target.read_text(encoding="utf-8") == "keep"


@pytest.mark.skipif(sys.platform == "win32", reason="the inode re-check is POSIX only")
def test_a_file_replaced_between_open_and_lock_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "x.lock"
    real = lock._try_lock
    swaps: list[Path] = []

    def swap_once(handle: int, where: Path) -> bool:
        if not swaps:
            # A holder released and removed the file after this open.
            swaps.append(where)
            os.unlink(where)
            where.write_bytes(b"")
        return real(handle, where)

    monkeypatch.setattr(lock, "_try_lock", swap_once)
    with lock.exclusive(path, "busy"):
        held = os.stat(path)
    assert swaps == [path]
    assert held.st_size == 0


@pytest.mark.skipif(sys.platform == "win32", reason="the inode re-check is POSIX only")
def test_a_file_that_keeps_moving_stops_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lock, "_still_at", lambda _handle, _path: False)
    with pytest.raises(ControllerError, match="kept being replaced"):
        with lock.exclusive(tmp_path / "x.lock", "busy"):
            pass


def test_a_platform_without_a_lock_primitive_refuses_to_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lock, "_FCNTL", None)
    monkeypatch.setattr(lock, "_MSVCRT", None)
    with pytest.raises(ControllerError, match="neither fcntl nor msvcrt"):
        with lock.exclusive(tmp_path / "x.lock", "busy"):
            pass


class _FakeMsvcrt:
    """`msvcrt.locking` semantics on any platform: one holder per path."""

    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(self, error: int = errno.EACCES) -> None:
        self.held: dict[int, int] = {}
        self.error = error

    def locking(self, handle: int, mode: int, _nbytes: int) -> None:
        inode = os.fstat(handle).st_ino
        if mode == self.LK_UNLCK:
            self.held.pop(inode, None)
            return
        if inode in self.held:
            raise OSError(self.error, "locked")
        self.held[inode] = handle


@pytest.mark.parametrize("busy_errno", sorted(lock._WINDOWS_BUSY))
def test_msvcrt_branch_reports_contention_as_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, busy_errno: int
) -> None:
    fake = _FakeMsvcrt(busy_errno)
    monkeypatch.setattr(lock, "_FCNTL", None)
    monkeypatch.setattr(lock, "_MSVCRT", fake)
    path = tmp_path / "x.lock"
    with lock.exclusive(path, "first"):
        with pytest.raises(ControllerError, match="^second$"):
            with lock.exclusive(path, "second"):
                pass
    assert fake.held == {}
    assert path.is_file()


def test_msvcrt_branch_reports_another_error_as_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = SimpleNamespace(
        LK_NBLCK=2,
        LK_UNLCK=0,
        locking=lambda *_args: (_ for _ in ()).throw(OSError(errno.EBADF, "bad handle")),
    )
    monkeypatch.setattr(lock, "_FCNTL", None)
    monkeypatch.setattr(lock, "_MSVCRT", fake)
    with pytest.raises(ControllerError, match="could not lock"):
        with lock.exclusive(tmp_path / "x.lock", "busy"):
            pass


def test_state_lock_creates_a_private_state_dir(tmp_path: Path) -> None:
    state = tmp_path / "state"
    with lock.state_lock(state):
        assert (state / lock.STATE_LOCK).exists()
        if os.name == "posix":
            assert state.stat().st_mode & 0o777 == 0o700
    assert [entry.name for entry in state.iterdir()] == [lock.STATE_LOCK]


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
def test_artifact_lock_is_keyed_by_the_real_path(tmp_path: Path) -> None:
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    artifact = real_dir / "a.json"
    artifact.write_text("{}", encoding="utf-8")
    # Another spelling of the same file, through a linked parent directory.
    (tmp_path / "alias").symlink_to(real_dir, target_is_directory=True)
    spelled = tmp_path / "alias" / "a.json"
    assert lock.artifact_lock_path(artifact) == lock.artifact_lock_path(spelled)
    other = tmp_path / "b.json"
    assert lock.artifact_lock_path(artifact) != lock.artifact_lock_path(other)
    with lock.artifact_lock(artifact):
        with pytest.raises(ControllerError, match="one controller per artifact"):
            with lock.artifact_lock(spelled):
                pass
        with lock.artifact_lock(other):
            pass


def test_artifact_lock_folds_case_in_the_name(tmp_path: Path) -> None:
    assert lock.artifact_lock_path(tmp_path / "A.json") == lock.artifact_lock_path(
        tmp_path / "a.json"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX link counts")
def test_a_hard_link_at_the_lock_path_is_refused_and_left_alone(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("keep", encoding="utf-8")
    path = tmp_path / "controller.lock"
    os.link(victim, path)
    with pytest.raises(ControllerError, match="expected one regular file"):
        with lock.exclusive(path, "busy"):
            pass
    assert victim.read_text(encoding="utf-8") == "keep"


def test_artifact_lock_ignores_tempdir_and_keeps_its_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "artifact.json"
    path = lock.artifact_lock_path(artifact)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "elsewhere"))
    assert lock.artifact_lock_path(artifact) == path
    assert path.parent == artifact.parent
    with lock.artifact_lock(artifact):
        assert path.is_file()
    assert path.is_file()
    with lock.artifact_lock(artifact):
        assert path.is_file()
