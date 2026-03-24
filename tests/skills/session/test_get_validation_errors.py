"""Tests for get_validation_errors.py GitHub Actions error extractor."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude" / "skills" / "session-log-fixer" / "scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))

import get_validation_errors


class TestGetRunIdFromPr:
    """Tests for _get_run_id_from_pr function."""

    @patch("get_validation_errors.subprocess.run")
    def test_finds_failed_run(self, mock_run):
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout=json.dumps({"headRefName": "feat/test"}),
            ),
            MagicMock(
                returncode=0,
                stdout=json.dumps([
                    {"databaseId": 100, "conclusion": "success"},
                    {"databaseId": 101, "conclusion": "failure"},
                ]),
            ),
        ]
        result = get_validation_errors._get_run_id_from_pr(42)
        assert result == "101"

    @patch("get_validation_errors.subprocess.run")
    def test_raises_when_no_failed_runs(self, mock_run):
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout=json.dumps({"headRefName": "feat/test"}),
            ),
            MagicMock(
                returncode=0,
                stdout=json.dumps([{"databaseId": 100, "conclusion": "success"}]),
            ),
        ]
        with pytest.raises(RuntimeError, match="No failed"):
            get_validation_errors._get_run_id_from_pr(42)

    @patch("get_validation_errors.subprocess.run")
    def test_raises_on_pr_fetch_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="err")
        with pytest.raises(RuntimeError, match="Failed to get PR"):
            get_validation_errors._get_run_id_from_pr(42)


class TestParseJobSummary:
    """Tests for _parse_job_summary function."""

    def test_extracts_verdict(self):
        summary = "Overall Verdict: **NON_COMPLIANT**"
        result = get_validation_errors._parse_job_summary(summary)
        assert result["overall_verdict"] == "NON_COMPLIANT"

    def test_extracts_must_count(self):
        summary = "3 MUST requirement(s) not met"
        result = get_validation_errors._parse_job_summary(summary)
        assert result["must_failure_count"] == 3

    def test_empty_summary(self):
        result = get_validation_errors._parse_job_summary("")
        assert result["overall_verdict"] is None
        assert result["must_failure_count"] == 0
        assert result["non_compliant_sessions"] == []

    def test_extracts_non_compliant_sessions(self):
        summary = (
            "| Session File | Status | MUST Failures |\n"
            "|---|---|---|\n"
            "| `session-1.json` | NON_COMPLIANT | 2 |\n"
        )
        result = get_validation_errors._parse_job_summary(summary)
        assert len(result["non_compliant_sessions"]) == 1
        assert result["non_compliant_sessions"][0]["file"] == "session-1.json"
        assert result["non_compliant_sessions"][0]["must_failures"] == 2

    def test_extracts_detailed_errors(self):
        summary = (
            "<summary> session-1.json</summary>\n"
            "| serenaActivated | MUST | FAIL | Not found |\n"
        )
        result = get_validation_errors._parse_job_summary(summary)
        assert "session-1.json" in result["detailed_errors"]
        assert len(result["detailed_errors"]["session-1.json"]) == 1
        assert result["detailed_errors"]["session-1.json"][0]["check"] == "serenaActivated"
