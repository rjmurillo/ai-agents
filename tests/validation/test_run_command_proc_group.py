"""Tests for _run_command and _run_command_bytes process-group teardown.

Covers Issue #4217: _run_command must kill the entire process group on timeout,
not just the direct child, so grandchildren (e.g. the gh-act artifact server)
do not survive to hold ports open.

Isolation controls:
- All tests import the module under test directly; no external tools needed.
- The killpg tests use mock.patch to verify the kill path fires on timeout.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validation import git_hook_policy as policy

# ---------------------------------------------------------------------------
# Positive: normal command executes and returns output
# ---------------------------------------------------------------------------


def test_run_command_success_returns_stdout(tmp_path: Path) -> None:
    """A fast command succeeds and stdout/stderr are captured."""
    result = policy._run_command(
        [sys.executable, "-c", "print('hello')"],
        tmp_path,
        timeout_seconds=5,
    )
    assert result.returncode == 0
    assert "hello" in result.stdout
    assert result.stderr == ""


def test_run_command_bytes_success_returns_bytes(tmp_path: Path) -> None:
    """Byte-mode variant returns bytes output on success."""
    result = policy._run_command_bytes(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'hi\\n')"],
        tmp_path,
        timeout_seconds=5,
    )
    assert result.returncode == 0
    assert b"hi" in result.stdout


def test_run_command_passes_input_text(tmp_path: Path) -> None:
    """input_text is written to stdin."""
    result = policy._run_command(
        [sys.executable, "-c", "import sys; print(sys.stdin.read().strip())"],
        tmp_path,
        input_text="sentinel_value",
        timeout_seconds=5,
    )
    assert result.returncode == 0
    assert "sentinel_value" in result.stdout


# ---------------------------------------------------------------------------
# Negative: timeout returns rc=3 with partial output
# ---------------------------------------------------------------------------


def test_run_command_timeout_returns_rc3(tmp_path: Path) -> None:
    """A timed-out command returns exit code 3 and includes a timeout message."""
    result = policy._run_command(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        tmp_path,
        timeout_seconds=1,
    )
    assert result.returncode == 3
    assert "timed out" in result.stderr


def test_run_command_bytes_timeout_returns_rc3(tmp_path: Path) -> None:
    """Byte-mode variant also returns rc=3 on timeout."""
    result = policy._run_command_bytes(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        tmp_path,
        timeout_seconds=1,
    )
    assert result.returncode == 3
    assert b"timed out" in result.stderr


def test_run_command_timeout_preserves_partial_stdout(tmp_path: Path) -> None:
    """Partial stdout written before the timeout is preserved."""
    script = "import sys, time; sys.stdout.write('partial\\n'); sys.stdout.flush(); time.sleep(30)"
    result = policy._run_command(
        [sys.executable, "-c", script],
        tmp_path,
        timeout_seconds=2,
    )
    assert result.returncode == 3
    assert "partial" in result.stdout


# ---------------------------------------------------------------------------
# Process-group kill: _killpg_safe is called on timeout (#4217)
#
# These tests verify that the timeout path calls _killpg_safe (which wraps
# os.killpg) by monkeypatching it and checking it fires with a PID argument.
# This is the load-bearing isolation: if _killpg_safe is never called, the
# grandchild survives.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX-only")
def test_run_command_calls_killpg_on_timeout(tmp_path: Path) -> None:
    """On timeout, _run_command calls _killpg_safe to kill the process group.

    Without this call, only the direct child is killed and grandchildren
    (e.g. the gh-act artifact server) survive to hold ports (Issue #4217).
    """
    killed_pids: list[int] = []
    original = policy._killpg_safe

    def recording(pid: int) -> None:
        killed_pids.append(pid)
        original(pid)

    with mock.patch.object(policy, "_killpg_safe", side_effect=recording):
        result = policy._run_command(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path,
            timeout_seconds=1,
        )

    assert result.returncode == 3
    assert len(killed_pids) >= 1, "_killpg_safe was never called on timeout"


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX-only")
def test_run_command_bytes_calls_killpg_on_timeout(tmp_path: Path) -> None:
    """Byte-mode variant also calls _killpg_safe on timeout."""
    killed_pids: list[int] = []
    original = policy._killpg_safe

    def recording(pid: int) -> None:
        killed_pids.append(pid)
        original(pid)

    with mock.patch.object(policy, "_killpg_safe", side_effect=recording):
        result = policy._run_command_bytes(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path,
            timeout_seconds=1,
        )

    assert result.returncode == 3
    assert len(killed_pids) >= 1, "_killpg_safe was never called on timeout (bytes mode)"


# ---------------------------------------------------------------------------
# Edge: _killpg_safe does not signal the caller's own process group
# ---------------------------------------------------------------------------


def test_killpg_safe_does_not_signal_own_group() -> None:
    """_killpg_safe called with our own PID must return without signalling us.

    Covers the guard: os.getpgid(pid) == os.getpgid(0) -> return early.
    If the guard is missing, the call would send SIGTERM to the hook itself.
    """
    policy._killpg_safe(os.getpid())  # must not raise or kill this process


def test_killpg_safe_handles_dead_pid_gracefully() -> None:
    """_killpg_safe called with a reaped PID must not raise."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    policy._killpg_safe(proc.pid)  # must not raise


# ---------------------------------------------------------------------------
# Isolation control: _SUPPORTS_PGROUP drives the killpg path
# ---------------------------------------------------------------------------


def test_supports_pgroup_is_true_on_posix() -> None:
    """Isolation: _SUPPORTS_PGROUP is True on POSIX so killpg fires on timeout.

    If _SUPPORTS_PGROUP is False on POSIX, start_new_session=False is passed,
    the child's pgid matches ours, the guard short-circuits, and no group kill
    happens. This is the silent bypass the fix must prevent.
    """
    assert policy._SUPPORTS_PGROUP is hasattr(os, "killpg")
    if hasattr(os, "killpg"):
        assert policy._SUPPORTS_PGROUP is True


# ---------------------------------------------------------------------------
# Isolation control: start_new_session=True is passed to Popen on POSIX
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX-only")
def test_run_command_passes_start_new_session_to_popen(tmp_path: Path) -> None:
    """Popen is called with start_new_session=True on POSIX (#4217 guard).

    If start_new_session=False, the child inherits our PGID. Then when
    _killpg_safe compares pgids, it short-circuits (same group = us), and no
    group kill fires. This test verifies the Popen call site passes True.
    """
    popen_calls: list[dict] = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        popen_calls.append({"start_new_session": kwargs.get("start_new_session")})
        return real_popen(*args, **kwargs)

    target = "scripts.validation.git_hook_policy.subprocess.Popen"
    with mock.patch(target, side_effect=recording_popen):
        policy._run_command(
            [sys.executable, "-c", "print('hi')"],
            tmp_path,
            timeout_seconds=5,
        )

    assert popen_calls, "Popen was never called"
    assert popen_calls[0]["start_new_session"] is True, (
        f"start_new_session={popen_calls[0]['start_new_session']!r}; expected True"
    )
