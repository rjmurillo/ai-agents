"""Tests for check_grade_changes.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
        / ".claude"
        / "skills"
        / "quality-grades"
        / "scripts"
    ),
)

from check_grade_changes import (
    find_degraded_domains,
    load_grades,
    main,
)


@pytest.fixture()
def sample_grades():
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
    def test_finds_degrading_trend(self, sample_grades):
        flagged = find_degraded_domains(sample_grades, threshold=60)
        domains = [d["domain"] for d in flagged]
        assert "memory" in domains

    def test_finds_below_threshold(self, sample_grades):
        flagged = find_degraded_domains(sample_grades, threshold=60)
        assert any(d["domain"] == "memory" for d in flagged)

    def test_skips_healthy_domains(self, sample_grades):
        flagged = find_degraded_domains(sample_grades, threshold=60)
        domains = [d["domain"] for d in flagged]
        assert "security" not in domains
        assert "qa" not in domains

    def test_counts_critical_gaps(self, sample_grades):
        flagged = find_degraded_domains(sample_grades, threshold=60)
        memory = next(d for d in flagged if d["domain"] == "memory")
        assert memory["critical_gaps"] == 1

    def test_empty_domains(self):
        flagged = find_degraded_domains({"domains": []}, threshold=60)
        assert flagged == []

    def test_all_healthy(self):
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
    def test_loads_valid_json(self, tmp_path, sample_grades):
        p = tmp_path / "grades.json"
        p.write_text(json.dumps(sample_grades), encoding="utf-8")
        data = load_grades(p)
        assert len(data["domains"]) == 3


class TestMain:
    def test_no_degradation_returns_zero(self, tmp_path):
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

    def test_missing_file_returns_one(self, tmp_path):
        result = main(["--grades-file", str(tmp_path / "missing.json")])
        assert result == 1

    def test_degradation_creates_issue(self, tmp_path, sample_grades):
        p = tmp_path / "grades.json"
        p.write_text(json.dumps(sample_grades), encoding="utf-8")
        with patch(
            "check_grade_changes.create_notification_issue"
        ) as mock_notify:
            result = main(["--grades-file", str(p)])
        assert result == 0
        mock_notify.assert_called_once()
        flagged = mock_notify.call_args[0][0]
        assert any(d["domain"] == "memory" for d in flagged)
