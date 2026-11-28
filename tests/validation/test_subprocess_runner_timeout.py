"""Timeout and baseline contract tests for the shared subprocess wrapper."""

from __future__ import annotations

import subprocess

import pytest

from scripts.validation import subprocess_runner
from scripts.validation.subprocess_runner import _decode_stream, _run_subprocess
from tests.validation.subprocess_runner_helpers import child
from tests.validation.subprocess_runner_timeout_helpers import (
    _CHILD_SLEEP,
    _TIMEOUT_SECONDS,
    _fake_popen,
    _TimedOutPopen,
)

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
        monkeypatch.setattr(
            subprocess_runner,
            "_terminate",
            lambda proc, _job=None: killed.append(proc),
        )
        monkeypatch.setattr(subprocess, "Popen", _fake_popen(proc))
        with pytest.raises(KeyboardInterrupt):
            _run_subprocess(["fake"], timeout=1)
        assert killed == [proc]
