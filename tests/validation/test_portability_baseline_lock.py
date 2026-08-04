"""Tests for the portable write-lock in portability_baseline._baseline_write_lock.

Issue #4237: the old mkdir-based lock was wedged permanently by a SIGKILL because
rmdir() never ran. The new implementation uses a file lock (fcntl.flock on POSIX,
msvcrt.locking on Windows) selected at import time so neither module is imported
on the wrong platform.

Platform coverage on this Linux host:
  POSIX path  -- exercised directly (this host is Linux).
  Windows path -- exercised through the _lock / _unlock injection seam.
    The seam accepts callables with signature ``(fd: int) -> None``.
    The underlying OS primitive is NOT called on Linux; behavior under a real
    msvcrt.locking call is not verified here and is so stated plainly.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from scripts.validation.portability_baseline import _baseline_write_lock

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _noop_lock(fd: int) -> None:
    """A lock primitive that succeeds immediately without any OS call."""


def _noop_unlock(fd: int) -> None:
    """An unlock primitive that succeeds immediately without any OS call."""


def _always_busy_lock(fd: int) -> None:
    """Simulates a lock that is always held by another process."""
    raise OSError("resource temporarily unavailable")


# ---------------------------------------------------------------------------
# POSIX path (exercised directly on this Linux host)
# ---------------------------------------------------------------------------


class TestPosixPath:
    """The real fcntl.flock path runs on this Linux host."""

    def test_lock_file_is_created_and_released(self, tmp_path: Path) -> None:
        lock_path = tmp_path / ".baseline.write-lock"
        with _baseline_write_lock(lock_path):
            assert lock_path.exists(), "lock file must exist while held"
        # File stays around after release (normal for file locks).
        # What matters is the context exits cleanly.

    def test_context_body_runs_exactly_once(self, tmp_path: Path) -> None:
        lock_path = tmp_path / ".baseline.write-lock"
        ran: list[int] = []
        with _baseline_write_lock(lock_path):
            ran.append(1)
        assert ran == [1]

    def test_stale_directory_from_old_mkdir_lock_is_removed(
        self, tmp_path: Path
    ) -> None:
        """A directory left by the previous SIGKILL-unsafe lock is cleaned up.

        Before Issue #4237 the lock was a directory created with mkdir().
        A SIGKILL left it in place and wedged every subsequent run. The new
        lock detects a directory at the lock path on entry and removes it.
        """
        lock_path = tmp_path / ".baseline.write-lock"
        lock_path.mkdir(mode=0o700)  # plant the stale artifact
        assert lock_path.is_dir()

        ran: list[int] = []
        with _baseline_write_lock(lock_path):
            ran.append(1)
        assert ran == [1], "stale directory must not prevent lock acquisition"

    def test_two_threads_do_not_interleave(self, tmp_path: Path) -> None:
        """Exclusive lock: a second thread waits while the first holds it."""
        lock_path = tmp_path / ".baseline.write-lock"
        log: list[str] = []
        errors: list[Exception] = []

        def writer(label: str, hold: float) -> None:
            try:
                with _baseline_write_lock(lock_path):
                    log.append(f"{label}:enter")
                    time.sleep(hold)
                    log.append(f"{label}:exit")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        t1 = threading.Thread(target=writer, args=("A", 0.08))
        t2 = threading.Thread(target=writer, args=("B", 0.0))
        t1.start()
        time.sleep(0.01)  # let t1 acquire first
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert not errors, errors
        # A:enter must precede B:enter, and A:exit must precede B:enter.
        assert log.index("A:enter") < log.index("A:exit")
        assert log.index("A:exit") < log.index("B:enter")


# ---------------------------------------------------------------------------
# Windows path (exercised via injection seam on this Linux host)
#
# The _lock and _unlock callables replace the platform-selected _lock_file
# and _unlock_file functions.  The msvcrt.locking primitive is NOT called;
# we verify the seam is wired, not that msvcrt works.
# ---------------------------------------------------------------------------


class TestWindowsPathViaSeam:
    """Windows msvcrt.locking path, exercised via the injection seam on Linux.

    These tests verify that _baseline_write_lock honours the injected
    primitives.  They do NOT call msvcrt.locking; that module does not exist
    on Linux.  A passing result here means the seam is wired; it does not
    mean the Windows path works end-to-end on a real Windows host.
    """

    def test_injected_lock_is_called(self, tmp_path: Path) -> None:
        lock_path = tmp_path / ".baseline.write-lock"
        calls: list[str] = []

        def record_lock(fd: int) -> None:
            calls.append("lock")

        def record_unlock(fd: int) -> None:
            calls.append("unlock")

        with _baseline_write_lock(lock_path, _lock=record_lock, _unlock=record_unlock):
            pass

        assert calls == ["lock", "unlock"], (
            "injected lock and unlock must each be called exactly once"
        )

    def test_unlock_is_called_even_when_body_raises(self, tmp_path: Path) -> None:
        lock_path = tmp_path / ".baseline.write-lock"
        calls: list[str] = []

        def record_lock(fd: int) -> None:
            calls.append("lock")

        def record_unlock(fd: int) -> None:
            calls.append("unlock")

        with pytest.raises(RuntimeError, match="body error"):
            with _baseline_write_lock(
                lock_path, _lock=record_lock, _unlock=record_unlock
            ):
                raise RuntimeError("body error")

        assert "unlock" in calls, "unlock must run even when the body raises"

    def test_stale_directory_is_cleared_before_injected_lock(
        self, tmp_path: Path
    ) -> None:
        lock_path = tmp_path / ".baseline.write-lock"
        lock_path.mkdir(mode=0o700)

        calls: list[str] = []

        def record_lock(fd: int) -> None:
            calls.append("lock")

        def record_unlock(fd: int) -> None:
            calls.append("unlock")

        with _baseline_write_lock(lock_path, _lock=record_lock, _unlock=record_unlock):
            pass

        assert calls == ["lock", "unlock"], (
            "stale directory must not prevent the injected lock from being called"
        )

    def test_timeout_fires_when_injected_lock_always_busy(
        self, tmp_path: Path
    ) -> None:
        """TimeoutError is raised when the lock primitive never succeeds."""
        lock_path = tmp_path / ".baseline.write-lock"

        import unittest.mock as mock

        # Patch time so the deadline expires on the very first check,
        # avoiding a real 10-second spin in the test suite.
        with mock.patch("scripts.validation.portability_baseline.time") as t:
            start = 0.0
            t.monotonic.side_effect = [
                start,       # initial: deadline = start + 10
                start + 11,  # first loop check: already past deadline
            ]
            t.sleep = lambda _: None

            with pytest.raises(TimeoutError, match="timed out waiting for baseline lock"):
                with _baseline_write_lock(
                    lock_path, _lock=_always_busy_lock, _unlock=_noop_unlock
                ):
                    pass
