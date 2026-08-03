"""Tests for scripts/ci/artifact_write_summary.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.artifact_write_summary import build_summary, main, run


class TestBuildSummary:
    def test_contains_header(self) -> None:
        s = build_summary("5", "2", "OK", "false")
        assert "## Artifact Insight Scanner Results" in s

    def test_contains_artifact_count(self) -> None:
        s = build_summary("10", "3", "PASS", "false")
        assert "10" in s

    def test_contains_finding_count(self) -> None:
        s = build_summary("4", "7", "PASS", "false")
        assert "7" in s

    def test_contains_verdict(self) -> None:
        s = build_summary("1", "0", "CRITICAL", "false")
        assert "CRITICAL" in s

    def test_dry_run_note_when_true(self) -> None:
        s = build_summary("0", "0", "N/A", "true")
        assert "Dry run mode" in s
        assert "[!NOTE]" in s

    def test_no_dry_run_note_when_false(self) -> None:
        s = build_summary("0", "0", "N/A", "false")
        assert "Dry run mode" not in s

    def test_table_rows_present(self) -> None:
        s = build_summary("3", "1", "PASS", "false")
        assert "| Artifacts Scanned |" in s
        assert "| Insights Found |" in s
        assert "| AI Verdict |" in s
        assert "| Dry Run |" in s


class TestRun:
    def test_writes_to_summary_file(self, tmp_path: Path) -> None:
        summary = tmp_path / "summary.md"
        env = {
            "ARTIFACT_COUNT": "5",
            "FINDING_COUNT": "2",
            "DRY_RUN": "false",
            "VERDICT": "PASS",
            "GITHUB_STEP_SUMMARY": str(summary),
        }
        with patch.dict(os.environ, env):
            rc = run()
        assert rc == 0
        content = summary.read_text()
        assert "Artifact Insight Scanner Results" in content

    def test_appends_to_existing_summary(self, tmp_path: Path) -> None:
        summary = tmp_path / "summary.md"
        summary.write_text("# Existing\n")
        env = {
            "GITHUB_STEP_SUMMARY": str(summary),
            "ARTIFACT_COUNT": "1",
            "FINDING_COUNT": "0",
            "DRY_RUN": "false",
            "VERDICT": "OK",
        }
        with patch.dict(os.environ, env):
            run()
        content = summary.read_text()
        assert "# Existing" in content
        assert "Artifact Insight Scanner Results" in content

    def test_stdout_when_no_summary_path(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            os.environ.update(
                {
                    "ARTIFACT_COUNT": "2",
                    "FINDING_COUNT": "1",
                    "VERDICT": "PASS",
                    "DRY_RUN": "false",
                }
            )
            run()
        out = capsys.readouterr().out
        assert "Artifact Insight Scanner Results" in out

    def test_dry_run_note_in_output(self, tmp_path: Path) -> None:
        summary = tmp_path / "summary.md"
        env = {
            "ARTIFACT_COUNT": "0",
            "FINDING_COUNT": "0",
            "DRY_RUN": "true",
            "VERDICT": "N/A",
            "GITHUB_STEP_SUMMARY": str(summary),
        }
        with patch.dict(os.environ, env):
            run()
        assert "Dry run mode" in summary.read_text()


class TestMain:
    def test_main_returns_0(self) -> None:
        with patch("scripts.ci.artifact_write_summary.run", return_value=0):
            assert main() == 0
