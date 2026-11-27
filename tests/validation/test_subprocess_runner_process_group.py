"""Process-group cleanup tests for the shared subprocess wrapper."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import subprocess_runner
from scripts.validation.subprocess_runner import _run_subprocess
from tests.validation.subprocess_runner_helpers import (
    POSIX_ONLY,
    child,
    kill_if_alive,
    read_pid,
    wait_dead,
)
from tests.validation.subprocess_runner_timeout_helpers import (
    _CHILD_SLEEP,
    _GRANDCHILD_PARENT,
    _TIMEOUT_SECONDS,
)

# ---------------------------------------------------------------------------
# _run_subprocess: the whole process group dies on timeout (issue #6412)
# ---------------------------------------------------------------------------


@POSIX_ONLY
class TestRunSubprocessTimeoutKillsProcessGroup:
    def test_grandchild_does_not_outlive_the_timeout(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "grandchild.pid"
        body = _GRANDCHILD_PARENT.format(extra="")
        grandchild = 0
        try:
            exit_code, stdout, stderr = _run_subprocess(
                [sys.executable, "-c", body, str(pid_file)], timeout=_TIMEOUT_SECONDS
            )
            grandchild = read_pid(pid_file)
            survived = not wait_dead(grandchild)
        finally:
            kill_if_alive(grandchild)

        assert exit_code == -1
        assert "PARENT-READY" in stdout, "partial output contract (#4955) must hold"
        assert f"Command timed out after {_TIMEOUT_SECONDS}s" in stderr
        assert survived is False, f"grandchild {grandchild} outlived the timed-out gate"

    def test_timeout_returns_promptly_when_a_grandchild_holds_the_pipe(
        self, tmp_path: Path
    ) -> None:
        """The read after the kill must not wait for the grandchild's 60s sleep."""
        pid_file = tmp_path / "grandchild.pid"
        body = _GRANDCHILD_PARENT.format(extra="")
        started = time.monotonic()
        try:
            _run_subprocess([sys.executable, "-c", body, str(pid_file)], timeout=_TIMEOUT_SECONDS)
        finally:
            grandchild = read_pid(pid_file)
            kill_if_alive(grandchild)
        assert time.monotonic() - started < 20

    def test_grandchild_that_escaped_the_group_cannot_hang_the_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A grandchild in its own session survives killpg and keeps the pipe open."""
        monkeypatch.setattr(subprocess_runner, "_DRAIN_TIMEOUT", 1)
        pid_file = tmp_path / "grandchild.pid"
        body = _GRANDCHILD_PARENT.format(extra=", start_new_session=True")
        started = time.monotonic()
        grandchild = 0
        try:
            exit_code, stdout, stderr = _run_subprocess(
                [sys.executable, "-c", body, str(pid_file)], timeout=_TIMEOUT_SECONDS
            )
            grandchild = read_pid(pid_file)
        finally:
            kill_if_alive(grandchild)

        assert time.monotonic() - started < 20
        assert exit_code == -1
        assert "PARENT-READY" in stdout
        assert f"Command timed out after {_TIMEOUT_SECONDS}s" in stderr

    def test_child_runs_in_its_own_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[object] = []
        real_popen = subprocess.Popen

        def recording(*args: Any, **kwargs: Any) -> subprocess.Popen[str]:
            seen.append(kwargs.get("start_new_session"))
            return real_popen(*args, **kwargs)  # subprocess-encoding: strict-ok

        monkeypatch.setattr(subprocess, "Popen", recording)
        _run_subprocess(child("print('hi')"))
        assert seen == [True]

    def test_timeout_terminates_the_child_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        killed: list[int] = []
        original = subprocess_runner._terminate

        def recording(proc: subprocess.Popen[str], _job: object | None = None) -> None:
            killed.append(proc.pid)
            original(proc)

        monkeypatch.setattr(subprocess_runner, "_terminate", recording)
        _run_subprocess(child(f"import time; time.sleep({_CHILD_SLEEP})"), timeout=1)
        assert len(killed) == 1 and killed[0] > 0

    def test_normal_exit_does_not_signal_any_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        killed: list[object] = []
        monkeypatch.setattr(
            subprocess_runner,
            "_terminate",
            lambda proc, _job=None: killed.append(proc),
        )
        exit_code, stdout, _stderr = _run_subprocess(child("print('fast')"))
        assert (exit_code, stdout.strip(), killed) == (0, "fast", [])

    def test_nonzero_exit_code_is_preserved(self) -> None:
        exit_code, _stdout, _stderr = _run_subprocess(child("import sys; sys.exit(7)"))
        assert exit_code == 7
