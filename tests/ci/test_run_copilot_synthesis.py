"""Tests for scripts/ci/run_copilot_synthesis.py.

Covers the PowerShell block extracted from copilot-context-synthesis.yml
(ADR-006 extraction). Tests: happy path (synthesis succeeds), failure
propagation (synthesis exits nonzero), configuration errors (missing or
invalid ISSUE_NUMBER), and the correct subprocess command is built.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_CI = Path(__file__).resolve().parents[2] / "scripts" / "ci"
_orig_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    import run_copilot_synthesis
    from run_copilot_synthesis import main
finally:
    sys.path[:] = _orig_path


class _SubprocessRecorder:
    """Records subprocess.run calls and replays canned exit codes."""

    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self._returncode = returncode

    def __call__(self, argv: list[str], **kwargs: object):
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(argv, self._returncode)


def _install(monkeypatch: pytest.MonkeyPatch, recorder: _SubprocessRecorder) -> None:
    monkeypatch.setattr(run_copilot_synthesis.subprocess, "run", recorder)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_success_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISSUE_NUMBER", "42")
    rec = _SubprocessRecorder(returncode=0)
    _install(monkeypatch, rec)
    assert main() == 0


def test_calls_synthesis_script(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISSUE_NUMBER", "99")
    rec = _SubprocessRecorder(returncode=0)
    _install(monkeypatch, rec)
    main()
    assert len(rec.calls) == 1
    cmd = rec.calls[0]
    assert cmd[0] == sys.executable
    assert "invoke_copilot_assignment.py" in cmd[1]
    assert "--issue-number" in cmd
    assert "99" in cmd


# ---------------------------------------------------------------------------
# Failure propagation
# ---------------------------------------------------------------------------


def test_synthesis_failure_returns_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISSUE_NUMBER", "42")
    rec = _SubprocessRecorder(returncode=1)
    _install(monkeypatch, rec)
    assert main() == 1


def test_synthesis_exit_3_also_returns_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any nonzero exit from the synthesis script maps to EXIT_FAILURE."""
    monkeypatch.setenv("ISSUE_NUMBER", "42")
    rec = _SubprocessRecorder(returncode=3)
    _install(monkeypatch, rec)
    assert main() == 1


# ---------------------------------------------------------------------------
# Configuration errors
# ---------------------------------------------------------------------------


def test_missing_issue_number_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ISSUE_NUMBER", raising=False)
    rec = _SubprocessRecorder()
    _install(monkeypatch, rec)
    assert main() == 2
    assert len(rec.calls) == 0  # subprocess not called


def test_empty_issue_number_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISSUE_NUMBER", "  ")
    rec = _SubprocessRecorder()
    _install(monkeypatch, rec)
    assert main() == 2
    assert len(rec.calls) == 0


def test_non_integer_issue_number_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISSUE_NUMBER", "abc")
    rec = _SubprocessRecorder()
    _install(monkeypatch, rec)
    assert main() == 2
    assert len(rec.calls) == 0


def test_float_issue_number_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISSUE_NUMBER", "3.14")
    rec = _SubprocessRecorder()
    _install(monkeypatch, rec)
    assert main() == 2


# ---------------------------------------------------------------------------
# Mutation guard: verifies each exit path is tested
# ---------------------------------------------------------------------------


def test_success_message_emitted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ISSUE_NUMBER", "7")
    rec = _SubprocessRecorder(returncode=0)
    _install(monkeypatch, rec)
    main()
    captured = capsys.readouterr()
    assert "7" in captured.out


def test_failure_message_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ISSUE_NUMBER", "7")
    rec = _SubprocessRecorder(returncode=1)
    _install(monkeypatch, rec)
    main()
    captured = capsys.readouterr()
    assert "7" in captured.err
