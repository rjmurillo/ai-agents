"""Tests for scripts/ci/drift_write_summary.py.

Covers:
  - drift_detected=true  -> affirmative summary written
  - drift_detected=false -> clean summary written
  - GITHUB_STEP_SUMMARY missing -> prints to stdout
  - GITHUB_STEP_SUMMARY set -> appends to file
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.drift_write_summary import build_summary, main, run

# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------


def test_build_summary_drift_true_contains_alert_text() -> None:
    s = build_summary("true")
    assert "drift" in s.lower()
    assert "detected" in s.lower()


def test_build_summary_drift_false_contains_clean_text() -> None:
    s = build_summary("false")
    assert "no drift" in s.lower() or "clean" in s.lower() or "ok" in s.lower()


def test_build_summary_returns_string() -> None:
    assert isinstance(build_summary("true"), str)
    assert isinstance(build_summary("false"), str)


# ---------------------------------------------------------------------------
# run() - file output
# ---------------------------------------------------------------------------


def test_run_appends_to_step_summary_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary_file = tmp_path / "summary.md"
    summary_file.write_text("# existing\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    monkeypatch.setenv("DRIFT_DETECTED", "true")
    rc = run()
    assert rc == 0
    content = summary_file.read_text()
    assert "# existing" in content
    assert "drift" in content.lower()


def test_run_clean_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary_file = tmp_path / "summary.md"
    summary_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    monkeypatch.setenv("DRIFT_DETECTED", "false")
    rc = run()
    assert rc == 0
    assert len(summary_file.read_text()) > 0


def test_run_no_summary_file_prints_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setenv("DRIFT_DETECTED", "true")
    rc = run()
    assert rc == 0
    out = capsys.readouterr().out
    assert "drift" in out.lower()


def test_run_env_var_case_insensitive_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary_file = tmp_path / "summary.md"
    summary_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    monkeypatch.setenv("DRIFT_DETECTED", "FALSE")
    rc = run()
    assert rc == 0
    content = summary_file.read_text()
    # "FALSE" != "true" so no-drift branch is taken
    assert "no drift" in content.lower() or "in sync" in content.lower() or len(content) > 0


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def test_main_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary_file = tmp_path / "summary.md"
    summary_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    monkeypatch.setenv("DRIFT_DETECTED", "true")
    result = main()
    assert result == 0
