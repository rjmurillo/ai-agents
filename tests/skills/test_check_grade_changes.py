"""Tests for check_grade_changes.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / ".claude" / "skills" / "quality-grades" / "scripts"),
)

from check_grade_changes import (
    create_notification_issue,
    find_degraded_domains,
    load_grades,
    main,
)


@pytest.fixture()
def sample_grades() -> dict:
    """Build a sample grades payload with stable, degrading, and improving domains."""
    return {
        "generated_at": "2026-03-07T00:00:00+00:00",
        "grading_agent": "quality-auditor",
        "domains": [
            {
                "domain": "security",
                "overall_grade": "A",
                "overall_score": 92.0,
                "trend": "stable",
                "layers": [],
            },
            {
                "domain": "memory",
                "overall_grade": "D",
                "overall_score": 45.0,
                "trend": "degrading",
                "layers": [
                    {
                        "layer": "tests",
                        "grade": "F",
                        "score": 20,
                        "file_count": 1,
                        "gaps": [
                            {
                                "layer": "tests",
                                "description": "Missing test coverage",
                                "severity": "critical",
                            }
                        ],
                    }
                ],
            },
            {
                "domain": "qa",
                "overall_grade": "B",
                "overall_score": 78.0,
                "trend": "improving",
                "layers": [],
            },
        ],
    }


class TestFindDegradedDomains:
    """Tests for identifying domains that are degrading or below threshold."""

    def test_finds_degrading_trend(self, sample_grades: dict) -> None:
        """Flag domains with a degrading trend."""
        flagged = find_degraded_domains(sample_grades, threshold=60)
        domains = [d["domain"] for d in flagged]
        assert "memory" in domains

    def test_finds_below_threshold(self, sample_grades: dict) -> None:
        """Flag domains with scores below the threshold."""
        flagged = find_degraded_domains(sample_grades, threshold=60)
        assert any(d["domain"] == "memory" for d in flagged)

    def test_skips_healthy_domains(self, sample_grades: dict) -> None:
        """Exclude healthy domains from flagged results."""
        flagged = find_degraded_domains(sample_grades, threshold=60)
        domains = [d["domain"] for d in flagged]
        assert "security" not in domains
        assert "qa" not in domains

    def test_counts_critical_gaps(self, sample_grades: dict) -> None:
        """Count critical gaps across layers for flagged domains."""
        flagged = find_degraded_domains(sample_grades, threshold=60)
        memory = next(d for d in flagged if d["domain"] == "memory")
        assert memory["critical_gaps"] == 1

    def test_empty_domains(self) -> None:
        """Return empty list when no domains exist in the data."""
        flagged = find_degraded_domains({"domains": []}, threshold=60)
        assert flagged == []

    def test_all_healthy(self) -> None:
        """Return empty list when all domains are above threshold and stable."""
        data = {
            "domains": [
                {
                    "domain": "foo",
                    "overall_grade": "A",
                    "overall_score": 95,
                    "trend": "stable",
                    "layers": [],
                }
            ]
        }
        flagged = find_degraded_domains(data, threshold=60)
        assert flagged == []


class TestLoadGrades:
    """Tests for loading grade data from JSON files."""

    def test_loads_valid_json(self, tmp_path: Path, sample_grades: dict) -> None:
        """Parse a valid JSON grades file and return all domains."""
        p = tmp_path / "grades.json"
        p.write_text(json.dumps(sample_grades), encoding="utf-8")
        data = load_grades(p)
        assert len(data["domains"]) == 3


class TestMain:
    """Tests for the main CLI entry point."""

    def test_no_degradation_returns_zero(self, tmp_path: Path) -> None:
        """Return exit code 0 when all domains are healthy."""
        data = {
            "domains": [
                {
                    "domain": "foo",
                    "overall_grade": "A",
                    "overall_score": 95,
                    "trend": "stable",
                    "layers": [],
                }
            ]
        }
        p = tmp_path / "grades.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        result = main(["--grades-file", str(p)])
        assert result == 0

    def test_missing_file_returns_one(self, tmp_path: Path) -> None:
        """Return exit code 1 when grades file does not exist."""
        result = main(["--grades-file", str(tmp_path / "missing.json")])
        assert result == 1

    def test_degradation_creates_issue(self, tmp_path: Path, sample_grades: dict) -> None:
        """Create notification issue when degraded domains are found."""
        p = tmp_path / "grades.json"
        p.write_text(json.dumps(sample_grades), encoding="utf-8")
        with patch("check_grade_changes.create_notification_issue") as mock_notify:
            result = main(["--grades-file", str(p)])
        assert result == 0
        mock_notify.assert_called_once()
        flagged = mock_notify.call_args[0][0]
        assert any(d["domain"] == "memory" for d in flagged)

    def test_gh_not_installed_returns_one(self, tmp_path: Path, sample_grades: dict) -> None:
        """Return exit code 1 when gh CLI is not installed."""
        p = tmp_path / "grades.json"
        p.write_text(json.dumps(sample_grades), encoding="utf-8")
        with patch(
            "check_grade_changes.subprocess.run",
            side_effect=FileNotFoundError("gh not found"),
        ):
            result = main(["--grades-file", str(p)])
        assert result == 1

    def test_gh_failure_returns_one(self, tmp_path: Path, sample_grades: dict) -> None:
        """Return exit code 1 when gh issue create fails."""
        p = tmp_path / "grades.json"
        p.write_text(json.dumps(sample_grades), encoding="utf-8")
        with patch(
            "check_grade_changes.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "gh"),
        ):
            result = main(["--grades-file", str(p)])
        assert result == 1


class TestCreateNotificationIssue:
    """Tests for error handling in create_notification_issue."""

    def test_raises_on_missing_gh(self) -> None:
        """Re-raise FileNotFoundError when gh is not installed."""
        flagged = [{"domain": "x", "grade": "F", "score": 10, "trend": "degrading", "critical_gaps": 0}]
        with patch(
            "check_grade_changes.subprocess.run",
            side_effect=FileNotFoundError("gh"),
        ):
            with pytest.raises(FileNotFoundError):
                create_notification_issue(flagged)

    def test_raises_on_gh_failure(self) -> None:
        """Re-raise CalledProcessError when gh command fails."""
        flagged = [{"domain": "x", "grade": "F", "score": 10, "trend": "degrading", "critical_gaps": 0}]
        with patch(
            "check_grade_changes.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "gh"),
        ):
            with pytest.raises(subprocess.CalledProcessError):
                create_notification_issue(flagged)
