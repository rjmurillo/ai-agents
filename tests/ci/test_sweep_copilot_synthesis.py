"""Tests for scripts/ci/sweep_copilot_synthesis.py.

Covers the PowerShell block extracted from copilot-context-synthesis.yml
(ADR-006 extraction). Tests: empty ISSUES is a no-op, multiple issues
processed in order, failed synthesis logged without failing the job,
gh label removal called on success, and label removal failure logged.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_CI = Path(__file__).resolve().parents[2] / "scripts" / "ci"
_orig_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    import sweep_copilot_synthesis
    from sweep_copilot_synthesis import _process_issue, main
finally:
    sys.path[:] = _orig_path


def _make_run(results: dict[str, int]) -> object:
    """Return a subprocess.run stub keyed by command list contents."""

    def _run(argv: list[str], **kwargs: object):
        cmd = argv[1] if len(argv) > 1 else argv[0]
        rc = results.get(cmd, 0)
        return subprocess.CompletedProcess(argv, rc, "", "")

    return _run


# ---------------------------------------------------------------------------
# Happy path: no issues
# ---------------------------------------------------------------------------


def test_empty_issues_is_no_op(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ISSUES", raising=False)
    assert main() == 0
    assert "No issues to process" in capsys.readouterr().out


def test_whitespace_only_issues_is_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISSUES", "   ")
    assert main() == 0


# ---------------------------------------------------------------------------
# Processing a single issue
# ---------------------------------------------------------------------------


def test_single_issue_success_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISSUES", "42")
    stub = _make_run({sweep_copilot_synthesis.sys.executable: 0, "gh": 0})
    with patch.object(sweep_copilot_synthesis.subprocess, "run", stub):
        assert main() == 0


def test_single_issue_failure_still_returns_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A synthesis failure is logged as a warning but does not fail the job."""
    monkeypatch.setenv("ISSUES", "42")
    stub = _make_run({sweep_copilot_synthesis._SYNTHESIS_SCRIPT: 1})
    with patch.object(sweep_copilot_synthesis.subprocess, "run", stub):
        assert main() == 0
    assert "::warning::" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Multiple issues
# ---------------------------------------------------------------------------


def test_multiple_issues_all_processed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISSUES", "1 2 3")
    calls: list[list[str]] = []

    def _run(argv: list[str], **kwargs: object):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    with patch.object(sweep_copilot_synthesis.subprocess, "run", _run):
        assert main() == 0

    synthesis_calls = [c for c in calls if "invoke_copilot_assignment.py" in str(c)]
    assert len(synthesis_calls) == 3


def test_partial_failures_count_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ISSUES", "1 2 3")
    call_count = [0]

    def _run(argv: list[str], **kwargs: object):
        if "invoke_copilot_assignment.py" in str(argv):
            call_count[0] += 1
            rc = 1 if call_count[0] == 2 else 0
        else:
            rc = 0
        return subprocess.CompletedProcess(argv, rc, "", "")

    with patch.object(sweep_copilot_synthesis.subprocess, "run", _run):
        assert main() == 0
    out = capsys.readouterr().out
    assert "Failed: 1" in out


# ---------------------------------------------------------------------------
# Label removal
# ---------------------------------------------------------------------------


def test_gh_label_removal_called_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def _run(argv: list[str], **kwargs: object):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    with patch.object(sweep_copilot_synthesis.subprocess, "run", _run):
        _process_issue("7")

    gh_calls = [c for c in calls if c and c[0] == "gh"]
    assert any("copilot-ready" in c for c in gh_calls)


def test_gh_label_failure_logged_as_warning(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _run(argv: list[str], **kwargs: object):
        rc = 1 if "gh" in str(argv) else 0
        return subprocess.CompletedProcess(argv, rc, "", "label error")

    with patch.object(sweep_copilot_synthesis.subprocess, "run", _run):
        result = _process_issue("7")

    assert result is True  # Issue itself succeeded
    assert "::warning::" in capsys.readouterr().out
