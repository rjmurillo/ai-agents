"""Shared helpers for the subprocess_runner process-tree tests (issue #6412)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

POSIX_ONLY = pytest.mark.skipif(not hasattr(os, "killpg"), reason="process groups are POSIX-only")


def child(body: str) -> list[str]:
    return [sys.executable, "-c", body]


def _proc_state(pid: int) -> str | None:
    """Return the state letter from ``/proc/<pid>/stat``, or None where /proc is absent."""
    try:
        return Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return None


def _ps_state(pid: int) -> str | None:
    """Return the state ``ps`` reports for ``pid`` (macOS has no /proc), or None."""
    try:
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def _exists(pid: int) -> bool:
    """True when the kernel still has an entry for ``pid``, zombie included."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def alive(pid: int) -> bool:
    """True when ``pid`` is a running process; a zombie awaiting reaping is dead."""
    if not _exists(pid):
        return False
    state = _proc_state(pid) or _ps_state(pid)
    if state is None:
        # No state to read: either no /proc and no ps, or the pid was reaped
        # after the first probe (issue #6621). Probe again to tell them apart.
        return _exists(pid)
    return not state.startswith("Z")


def kill_if_alive(pid: int) -> None:
    """SIGKILL ``pid`` when it still runs. A process that exits first is not an error.

    The group kill can land between the ``alive`` check and ``os.kill``, so the
    process may already be gone (issue #6621). Pid 0 means no pid was read.
    """
    if not pid or not alive(pid):
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def wait_dead(pid: int, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return not alive(pid)


def read_pid(pid_file: Path) -> int:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        text = pid_file.read_text(encoding="utf-8") if pid_file.exists() else ""
        if text:
            return int(text)
        time.sleep(0.05)
    raise AssertionError("grandchild pid file was never written")
