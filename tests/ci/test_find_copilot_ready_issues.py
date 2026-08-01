"""Tests for scripts/ci/find_copilot_ready_issues.py.

Covers the bash block extracted from copilot-context-synthesis.yml
(ADR-006 extraction). Tests: zero-issue result, multi-issue result,
GITHUB_OUTPUT writes, gh CLI failure, and missing env var.
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
    import find_copilot_ready_issues
    from find_copilot_ready_issues import main
finally:
    sys.path[:] = _orig_path


class _GhRecorder:
    """Simulates gh CLI responses."""

    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self._stdout = stdout
        self._returncode = returncode

    def __call__(self, argv: list[str], **kwargs: object):
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(argv, self._returncode, self._stdout)


def _install(monkeypatch: pytest.MonkeyPatch, recorder: _GhRecorder) -> None:
    monkeypatch.setattr(find_copilot_ready_issues.subprocess, "run", recorder)


# ---------------------------------------------------------------------------
# Happy path: zero issues
# ---------------------------------------------------------------------------


def test_zero_issues_writes_count_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_file = tmp_path / "output"
    output_file.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    rec = _GhRecorder(stdout="")
    _install(monkeypatch, rec)
    assert main() == 0
    content = output_file.read_text()
    assert "issues=\n" in content
    assert "count=0\n" in content


def test_zero_issues_prints_none_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_file = tmp_path / "output"
    output_file.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    rec = _GhRecorder(stdout="")
    _install(monkeypatch, rec)
    main()
    assert "No issues found" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Happy path: multiple issues
# ---------------------------------------------------------------------------


def test_three_issues_writes_space_separated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_file = tmp_path / "output"
    output_file.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    rec = _GhRecorder(stdout="101\n202\n303\n")
    _install(monkeypatch, rec)
    assert main() == 0
    content = output_file.read_text()
    assert "issues=101 202 303\n" in content
    assert "count=3\n" in content


def test_single_issue_writes_one_number(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_file = tmp_path / "output"
    output_file.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    rec = _GhRecorder(stdout="55\n")
    _install(monkeypatch, rec)
    assert main() == 0
    content = output_file.read_text()
    assert "issues=55\n" in content
    assert "count=1\n" in content


# ---------------------------------------------------------------------------
# gh CLI failure
# ---------------------------------------------------------------------------


def test_gh_failure_returns_exit_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When gh fails the step must fail (match bash set -eo pipefail original)."""
    output_file = tmp_path / "output"
    output_file.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    rec = _GhRecorder(returncode=1)
    _install(monkeypatch, rec)
    assert main() == find_copilot_ready_issues.EXIT_FAILURE
    # No output should be written on failure
    assert output_file.read_text() == ""


# ---------------------------------------------------------------------------
# Configuration error
# ---------------------------------------------------------------------------


def test_missing_github_output_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    rec = _GhRecorder()
    _install(monkeypatch, rec)
    assert main() == 2
    assert len(rec.calls) == 0


# ---------------------------------------------------------------------------
# Mutation guards
# ---------------------------------------------------------------------------


def test_gh_command_requests_copilot_ready_label(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_file = tmp_path / "output"
    output_file.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    rec = _GhRecorder(stdout="1\n")
    _install(monkeypatch, rec)
    main()
    assert len(rec.calls) == 1
    cmd = rec.calls[0]
    assert "copilot-ready" in cmd
    assert "--state" in cmd
    assert "open" in cmd


def test_count_matches_number_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """count= must match the actual number of issue IDs written to issues=."""
    output_file = tmp_path / "output"
    output_file.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    rec = _GhRecorder(stdout="10\n20\n")
    _install(monkeypatch, rec)
    main()
    content = output_file.read_text()
    # Extract values
    issues_line = next(line for line in content.splitlines() if line.startswith("issues="))
    count_line = next(line for line in content.splitlines() if line.startswith("count="))
    issues_val = issues_line[len("issues=") :]
    count_val = int(count_line[len("count=") :])
    assert count_val == len(issues_val.split())


def test_gh_failure_exit_code_propagated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Mutant guard: swallowing the gh error (returning EXIT_SUCCESS) must die."""
    output_file = tmp_path / "output"
    output_file.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    # gh exits 2 (auth failure); must propagate as EXIT_FAILURE
    rec = _GhRecorder(returncode=2)
    _install(monkeypatch, rec)
    rc = main()
    assert rc == find_copilot_ready_issues.EXIT_FAILURE
    assert rc != find_copilot_ready_issues.EXIT_SUCCESS
