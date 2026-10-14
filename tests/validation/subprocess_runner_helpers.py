"""Shared helpers for the subprocess_runner process-tree tests (issue #6412)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

POSIX_ONLY = pytest.mark.skipif(not hasattr(os, "killpg"), reason="process groups are POSIX-only")


def child(body: str) -> list[str]:
    return [sys.executable, "-c", body]


def alive(pid: int) -> bool:
    """True when ``pid`` is a running process; a zombie awaiting reaping is dead."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return True
    return state != "Z"


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
