"""Tests for the shared subprocess wrapper (issue #4955).

``_run_subprocess`` used to discard the partial stdout and stderr Python
preserves on ``subprocess.TimeoutExpired``. A merge-tree ratchet that flushed
its result and then exceeded the timeout reported only the timeout, hiding the
diagnostic that explained where it stopped (issue #4876). These tests pin the
repaired contract: partial output is surfaced, the timeout stays a failure, and
the timeout marker stays present.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from scripts.validation.subprocess_runner import _decode_stream, _run_subprocess

# A child that flushes its streams, then sleeps well past any test timeout. The
# 1-second wrapper timeout fires first, so the sleep duration only has to exceed
# it comfortably; the test never waits the full sleep.
_TIMEOUT_SECONDS = 1
_CHILD_SLEEP = 30


def _child(body: str) -> list[str]:
    return [sys.executable, "-c", body]


def _raise_timeout(output: bytes | str | None, stderr: bytes | str | None) -> object:
    """Return a fake ``subprocess.run`` that raises ``TimeoutExpired``.

    Lets a test control the exact ``stdout``/``stderr`` types the exception
    carries, including the ``str`` values only the Windows
    kill-then-communicate path produces (unreachable on the POSIX CI host).
    """

    def _fake_run(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(
            cmd=["fake"],
            timeout=_TIMEOUT_SECONDS,
            output=output,
            stderr=stderr,
        )

    return _fake_run


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
            _child("import sys; sys.stdout.write('out'); sys.stderr.write('err')")
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
        exit_code, stdout, stderr = _run_subprocess(_child(body), timeout=_TIMEOUT_SECONDS)

        assert exit_code == -1, "a timeout must stay a failure, not become success"
        assert "RATCHET-RESULT" in stdout
        assert "DIAGNOSTIC" in stderr
        assert f"Command timed out after {_TIMEOUT_SECONDS}s" in stderr

    def test_no_output_reports_only_the_marker(self) -> None:
        body = f"import time; time.sleep({_CHILD_SLEEP})"
        exit_code, stdout, stderr = _run_subprocess(_child(body), timeout=_TIMEOUT_SECONDS)

        assert exit_code == -1
        assert stdout == ""
        assert stderr == f"Command timed out after {_TIMEOUT_SECONDS}s"

    def test_non_utf8_partial_output_uses_replacement(self) -> None:
        body = (
            "import sys, time;"
            "sys.stdout.buffer.write(b'\\xff\\xfe raw');sys.stdout.buffer.flush();"
            f"time.sleep({_CHILD_SLEEP})"
        )
        exit_code, stdout, stderr = _run_subprocess(_child(body), timeout=_TIMEOUT_SECONDS)

        assert exit_code == -1
        assert "\ufffd" in stdout, "invalid bytes must decode with U+FFFD, not crash"
        assert f"Command timed out after {_TIMEOUT_SECONDS}s" in stderr


# ---------------------------------------------------------------------------
# _run_subprocess: timeout path branches driven with a faked run
# ---------------------------------------------------------------------------


class TestRunSubprocessTimeoutFaked:
    def test_stderr_only_child_keeps_marker_after_partial(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _raise_timeout(None, b"boom"))
        exit_code, stdout, stderr = _run_subprocess(["fake"], timeout=5)
        assert exit_code == -1
        assert stdout == ""
        assert stderr == "boom\nCommand timed out after 5s"

    def test_windows_str_attributes_are_not_double_decoded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The Windows path leaves ``str`` on the exception; pass it through."""
        monkeypatch.setattr(subprocess, "run", _raise_timeout("win-out", "win-err"))
        exit_code, stdout, stderr = _run_subprocess(["fake"], timeout=2)
        assert exit_code == -1
        assert stdout == "win-out"
        assert stderr == "win-err\nCommand timed out after 2s"

    def test_populated_output_never_flips_timeout_to_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(subprocess, "run", _raise_timeout(b"partial", b"partial"))
        exit_code, _stdout, _stderr = _run_subprocess(["fake"], timeout=3)
        assert exit_code == -1
