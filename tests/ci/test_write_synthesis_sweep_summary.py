"""Tests for scripts/ci/write_synthesis_sweep_summary.py.

Covers the bash block extracted from copilot-context-synthesis.yml
(ADR-006 extraction). Tests: zero-count path, nonzero-count path,
GITHUB_STEP_SUMMARY write, invalid count falls back to zero, and
missing GITHUB_STEP_SUMMARY returns EXIT_CONFIG.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS_CI = Path(__file__).resolve().parents[2] / "scripts" / "ci"
_orig_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    from write_synthesis_sweep_summary import build_sweep_summary, main
finally:
    sys.path[:] = _orig_path


# ---------------------------------------------------------------------------
# build_sweep_summary unit tests
# ---------------------------------------------------------------------------


def test_zero_count_contains_all_caught_up() -> None:
    result = build_sweep_summary("schedule", 0, "")
    assert "All caught up" in result
    assert "Issues Processed" not in result


def test_nonzero_count_contains_issues_processed() -> None:
    result = build_sweep_summary("workflow_dispatch", 3, "1 2 3")
    assert "Issues Processed" in result
    assert "All caught up" not in result
    assert "1 2 3" in result


def test_trigger_in_output() -> None:
    result = build_sweep_summary("schedule", 0, "")
    assert "schedule" in result


def test_count_in_output() -> None:
    result = build_sweep_summary("push", 5, "1 2 3 4 5")
    assert "5" in result


# ---------------------------------------------------------------------------
# main integration tests
# ---------------------------------------------------------------------------


def test_writes_to_summary_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    summary = tmp_path / "step_summary"
    summary.write_text("")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("TRIGGER", "schedule")
    monkeypatch.setenv("ISSUES_COUNT", "0")
    monkeypatch.setenv("ISSUES", "")
    assert main() == 0
    content = summary.read_text()
    assert "Copilot Context Synthesis Sweep" in content


def test_zero_count_writes_all_caught_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    summary = tmp_path / "step_summary"
    summary.write_text("")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("TRIGGER", "schedule")
    monkeypatch.setenv("ISSUES_COUNT", "0")
    monkeypatch.setenv("ISSUES", "")
    main()
    assert "All caught up" in summary.read_text()


def test_nonzero_count_writes_issues_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    summary = tmp_path / "step_summary"
    summary.write_text("")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("TRIGGER", "workflow_dispatch")
    monkeypatch.setenv("ISSUES_COUNT", "2")
    monkeypatch.setenv("ISSUES", "10 20")
    main()
    content = summary.read_text()
    assert "10 20" in content
    assert "Issues Processed" in content


def test_invalid_count_falls_back_to_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    summary = tmp_path / "step_summary"
    summary.write_text("")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("TRIGGER", "push")
    monkeypatch.setenv("ISSUES_COUNT", "not-a-number")
    monkeypatch.setenv("ISSUES", "")
    assert main() == 0
    assert "All caught up" in summary.read_text()


def test_missing_summary_path_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert main() == 2


def test_appends_not_overwrites(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    summary = tmp_path / "step_summary"
    summary.write_text("existing content\n")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("TRIGGER", "schedule")
    monkeypatch.setenv("ISSUES_COUNT", "0")
    monkeypatch.setenv("ISSUES", "")
    main()
    content = summary.read_text()
    assert content.startswith("existing content\n")
    assert "Copilot Context Synthesis Sweep" in content
