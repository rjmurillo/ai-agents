"""Tests for the shared subprocess wrapper (issue #4955).

``_run_subprocess`` used to discard the partial stdout and stderr Python
preserves on ``subprocess.TimeoutExpired``. A merge-tree ratchet that flushed
its result and then exceeded the timeout reported only the timeout, hiding the
diagnostic that explained where it stopped (issue #4876). These tests pin the
repaired contract: partial output is surfaced, the timeout stays a failure, and
the timeout marker stays present.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import subprocess_runner
from scripts.validation.subprocess_runner import _decode_stream, _run_subprocess
from tests.validation.subprocess_runner_helpers import (
    POSIX_ONLY,
    alive,
    child,
    read_pid,
    wait_dead,
)

# A child that flushes its streams, then sleeps well past any test timeout. The
# 1-second wrapper timeout fires first, so the sleep duration only has to exceed
# it comfortably; the test never waits the full sleep.
_TIMEOUT_SECONDS = 1
_CHILD_SLEEP = 30


class _TimedOutPopen:
    """Fake ``Popen`` whose first ``communicate`` times out.

    Lets a test control the exact ``stdout``/``stderr`` types the exception
    carries, including the ``str`` values only the Windows
    kill-then-communicate path produces (unreachable on the POSIX CI host).
    ``drained`` is what the post-kill ``communicate`` returns; ``None`` makes
    that second call time out again, as it does when a grandchild escaped the
    group and still holds the pipe.
    """

    pid = 0
    returncode = -9

    def __init__(
        self,
        output: bytes | str | None,
        stderr: bytes | str | None,
        drained: tuple[str, str] | None = ("", ""),
    ) -> None:
        self._output = output
        self._stderr = stderr
        self._drained = drained
        self.calls = 0
        self.killed = False
        self.stdout = None
        self.stderr = None

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        self.calls += 1
        if self.calls == 1 or self._drained is None:
            raise subprocess.TimeoutExpired(
                cmd=["fake"], timeout=_TIMEOUT_SECONDS, output=self._output, stderr=self._stderr
            )
        return self._drained

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def __enter__(self) -> _TimedOutPopen:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _fake_popen(proc: _TimedOutPopen) -> object:
    def _factory(*_args: object, **_kwargs: object) -> _TimedOutPopen:
        return proc

    return _factory


# ---------------------------------------------------------------------------
# _decode_stream
# ---------------------------------------------------------------------------


class TestDecodeStream:
    def test_none_becomes_empty_string(self) -> None:
        assert _decode_stream(None) == ""

    def test_str_passes_through_unchanged(self) -> None:
        assert _decode_stream("already text") == "already text"

    def test_utf8_bytes_decode(self) -> None:
        assert _decode_stream("café".encode()) == "café"

    def test_non_utf8_bytes_use_replacement(self) -> None:
        # 0xFF is invalid UTF-8; the replace codec yields U+FFFD.
        decoded = _decode_stream(b"raw\xff")
        assert decoded == "raw\ufffd"


# ---------------------------------------------------------------------------
# _run_subprocess: happy path and command-not-found (unchanged behavior)
# ---------------------------------------------------------------------------


class TestRunSubprocessBaseline:
    def test_normal_completion_preserves_output(self) -> None:
        exit_code, stdout, stderr = _run_subprocess(
            child("import sys; sys.stdout.write('out'); sys.stderr.write('err')")
        )
        assert exit_code == 0
        assert stdout == "out"
        assert stderr == "err"

    def test_command_not_found_returns_marker(self) -> None:
        exit_code, stdout, stderr = _run_subprocess(["nonexistent_command_xyz_123"])
        assert exit_code == -1
        assert stdout == ""
        assert "Command not found" in stderr


# ---------------------------------------------------------------------------
# _run_subprocess: timeout path (issue #4955) with real children
# ---------------------------------------------------------------------------


class TestRunSubprocessTimeoutRealChild:
    def test_partial_stdout_and_stderr_reach_the_failure(self) -> None:
        """The merge-tree wrapper contract: flushed output reaches the caller."""
        body = (
            "import sys, time;"
            "sys.stdout.write('RATCHET-RESULT');sys.stdout.flush();"
            "sys.stderr.write('DIAGNOSTIC');sys.stderr.flush();"
            f"time.sleep({_CHILD_SLEEP})"
        )
        exit_code, stdout, stderr = _run_subprocess(child(body), timeout=_TIMEOUT_SECONDS)

        assert exit_code == -1, "a timeout must stay a failure, not become success"
        assert "RATCHET-RESULT" in stdout
        assert "DIAGNOSTIC" in stderr
        assert f"Command timed out after {_TIMEOUT_SECONDS}s" in stderr

    def test_no_output_reports_only_the_marker(self) -> None:
        body = f"import time; time.sleep({_CHILD_SLEEP})"
        exit_code, stdout, stderr = _run_subprocess(child(body), timeout=_TIMEOUT_SECONDS)

        assert exit_code == -1
        assert stdout == ""
        assert stderr == f"Command timed out after {_TIMEOUT_SECONDS}s"

    def test_non_utf8_partial_output_uses_replacement(self) -> None:
        body = (
            "import sys, time;"
            "sys.stdout.buffer.write(b'\\xff\\xfe raw');sys.stdout.buffer.flush();"
            f"time.sleep({_CHILD_SLEEP})"
        )
        exit_code, stdout, stderr = _run_subprocess(child(body), timeout=_TIMEOUT_SECONDS)

        assert exit_code == -1
        assert "\ufffd" in stdout, "invalid bytes must decode with U+FFFD, not crash"
        assert f"Command timed out after {_TIMEOUT_SECONDS}s" in stderr


# ---------------------------------------------------------------------------
# _run_subprocess: timeout path branches driven with a faked run
# ---------------------------------------------------------------------------


class TestRunSubprocessTimeoutFaked:
    @pytest.fixture(autouse=True)
    def _no_real_group_kill(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The fake pid 0 must never reach a real ``killpg``."""
        monkeypatch.setattr(subprocess_runner, "_signal_group", lambda _pgid, _sig: None)

    def test_stderr_only_child_keeps_marker_after_partial(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proc = _TimedOutPopen(None, b"boom")
        monkeypatch.setattr(subprocess, "Popen", _fake_popen(proc))
        exit_code, stdout, stderr = _run_subprocess(["fake"], timeout=5)
        assert exit_code == -1
        assert stdout == ""
        assert stderr == "boom\nCommand timed out after 5s"

    def test_windows_str_attributes_are_not_double_decoded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The Windows path leaves ``str`` on the exception; pass it through."""
        proc = _TimedOutPopen("win-out", "win-err")
        monkeypatch.setattr(subprocess, "Popen", _fake_popen(proc))
        exit_code, stdout, stderr = _run_subprocess(["fake"], timeout=2)
        assert exit_code == -1
        assert stdout == "win-out"
        assert stderr == "win-err\nCommand timed out after 2s"

    def test_populated_output_never_flips_timeout_to_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proc = _TimedOutPopen(b"partial", b"partial")
        monkeypatch.setattr(subprocess, "Popen", _fake_popen(proc))
        exit_code, _stdout, _stderr = _run_subprocess(["fake"], timeout=3)
        assert exit_code == -1

    def test_drained_output_wins_over_the_first_partial(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The post-kill read holds everything the child wrote, so it replaces the partial."""
        proc = _TimedOutPopen(b"early", b"early-err", drained=("all-out", "all-err"))
        monkeypatch.setattr(subprocess, "Popen", _fake_popen(proc))
        exit_code, stdout, stderr = _run_subprocess(["fake"], timeout=4)
        assert exit_code == -1
        assert stdout == "all-out"
        assert stderr == "all-err\nCommand timed out after 4s"

    def test_drain_that_times_out_again_keeps_the_partial(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A grandchild that escaped the group still holds the pipe; do not hang."""
        proc = _TimedOutPopen(b"seen", b"seen-err", drained=None)
        monkeypatch.setattr(subprocess, "Popen", _fake_popen(proc))
        exit_code, stdout, stderr = _run_subprocess(["fake"], timeout=6)
        assert exit_code == -1
        assert stdout == "seen"
        assert stderr == "seen-err\nCommand timed out after 6s"

    def test_non_posix_host_kills_the_direct_child_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        proc = _TimedOutPopen(None, None)
        monkeypatch.setattr(subprocess_runner, "_SUPPORTS_PGROUP", False)
        monkeypatch.setattr(subprocess, "Popen", _fake_popen(proc))
        exit_code, _stdout, stderr = _run_subprocess(["fake"], timeout=7)
        assert exit_code == -1
        assert proc.killed is True
        assert stderr == "Command timed out after 7s"

    def test_interrupt_kills_the_group_and_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        killed: list[object] = []

        class _Interrupted(_TimedOutPopen):
            def communicate(self, timeout: float | None = None) -> tuple[str, str]:
                raise KeyboardInterrupt

        proc = _Interrupted(None, None)
        monkeypatch.setattr(subprocess_runner, "_terminate", killed.append)
        monkeypatch.setattr(subprocess, "Popen", _fake_popen(proc))
        with pytest.raises(KeyboardInterrupt):
            _run_subprocess(["fake"], timeout=1)
        assert killed == [proc]


# ---------------------------------------------------------------------------
# _run_subprocess: the whole process group dies on timeout (issue #6412)
# ---------------------------------------------------------------------------

# Spawns a grandchild that sleeps, records its pid, flushes a marker, then sleeps
# itself. ``{extra}`` lets a test change how the grandchild is launched.
_GRANDCHILD_PARENT = (
    "import subprocess, sys, time;"
    "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']{extra});"
    "open(sys.argv[1], 'w').write(str(g.pid));"
    "sys.stdout.write('PARENT-READY');sys.stdout.flush();"
    "time.sleep(60)"
)


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
            if grandchild and alive(grandchild):
                os.kill(grandchild, 9)

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
            if alive(grandchild):
                os.kill(grandchild, 9)
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
            if grandchild and alive(grandchild):
                os.kill(grandchild, 9)

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

        def recording(proc: subprocess.Popen[str]) -> None:
            killed.append(proc.pid)
            original(proc)

        monkeypatch.setattr(subprocess_runner, "_terminate", recording)
        _run_subprocess(child(f"import time; time.sleep({_CHILD_SLEEP})"), timeout=1)
        assert len(killed) == 1 and killed[0] > 0

    def test_normal_exit_does_not_signal_any_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        killed: list[object] = []
        monkeypatch.setattr(subprocess_runner, "_terminate", killed.append)
        exit_code, stdout, _stderr = _run_subprocess(child("print('fast')"))
        assert (exit_code, stdout.strip(), killed) == (0, "fast", [])

    def test_nonzero_exit_code_is_preserved(self) -> None:
        exit_code, _stdout, _stderr = _run_subprocess(child("import sys; sys.exit(7)"))
        assert exit_code == 7
