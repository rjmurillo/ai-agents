"""Native Windows integration for ordinary owned validator processes."""

from __future__ import annotations

import ctypes
import sys
import time

import pytest

from scripts.validation.subprocess_runner import _run_subprocess

pytestmark = [
    pytest.mark.windows_path,
    pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows jobs"),
]


def _assert_process_exited(pid: int) -> None:
    # Query only the two process IDs emitted by the benign test program.
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    wait = kernel32.WaitForSingleObject
    wait.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    wait.restype = wintypes.DWORD
    close = kernel32.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL

    handle = open_process(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        # ERROR_INVALID_PARAMETER: the terminated process no longer exists.
        assert ctypes.get_last_error() == 87
        return
    try:
        assert wait(handle, 5000) == 0, f"owned process {pid} did not exit"
    finally:
        assert close(handle)


def test_native_windows_job_resumes_and_completes(capsys: pytest.CaptureFixture[str]) -> None:
    result = _run_subprocess(
        [sys.executable, "-c", "import sys; print('ready'); print('done', file=sys.stderr)"],
        timeout=10,
    )

    assert result == (0, "ready\n", "done\n")
    assert not capsys.readouterr().err


def test_native_windows_timeout_reaps_owned_child_and_grandchild(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Both processes have finite lifetimes even if job cleanup regresses. The
    # grandchild inherits stdout and stderr, so its exit also releases the pipes.
    grandchild = (
        "import os, sys, time; "
        "print(f'grandchild:{os.getpid()}', flush=True); "
        "print('grandchild ready', file=sys.stderr, flush=True); time.sleep(40)"
    )
    child = (
        "import os, subprocess, sys, time; "
        "print(f'child:{os.getpid()}', flush=True); "
        "print('child ready', file=sys.stderr, flush=True); "
        "subprocess.Popen([sys.executable, '-c', sys.argv[1]]); time.sleep(40)"
    )
    started = time.monotonic()
    code, stdout, stderr = _run_subprocess([sys.executable, "-c", child, grandchild], timeout=10)
    elapsed = time.monotonic() - started

    assert code == -1
    assert "Command timed out after 10s" in stderr
    assert "child ready" in stderr.splitlines()
    assert "grandchild ready" in stderr.splitlines()
    assert not capsys.readouterr().err  # Neither ownership nor termination downgraded.
    assert elapsed < 25, f"deadline and pipe drain took {elapsed:.1f}s"
    pids = dict(line.split(":", 1) for line in stdout.splitlines())
    assert set(pids) == {"child", "grandchild"}
    assert pids["child"] != pids["grandchild"]
    for pid in pids.values():
        _assert_process_exited(int(pid))
