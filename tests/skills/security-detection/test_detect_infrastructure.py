#!/usr/bin/env python3
"""Tests for the detect_infrastructure() aggregation function."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from detect_infrastructure_test_helpers import detect_infrastructure, mod


def test_detect_infrastructure_can_source_staged_files() -> None:
    with patch.object(mod, "get_staged_files", return_value=["Dockerfile"]):
        result = detect_infrastructure(use_git_staged=True)

    assert result["highest_risk"] == "high"
    assert result["file_count"] == 1


class TestDetectInfrastructure:
    """Tests for detect_infrastructure function."""

    def test_empty_files_returns_no_findings(self) -> None:
        result = detect_infrastructure(changed_files=[])
        assert result["findings"] == []
        assert result["highest_risk"] == "none"
        assert result["file_count"] == 0

    def test_none_files_returns_no_findings(self) -> None:
        result = detect_infrastructure(changed_files=None)
        assert result["findings"] == []

    def test_no_arguments_returns_no_findings(self) -> None:
        result = detect_infrastructure()
        assert result["findings"] == []
        assert result["file_count"] == 0

    def test_detects_critical_files(self) -> None:
        result = detect_infrastructure(changed_files=[".github/workflows/ci.yml"])
        assert len(result["findings"]) == 1
        assert result["highest_risk"] == "critical"
        assert result["findings"][0]["RiskLevel"] == "critical"

    def test_detects_high_files(self) -> None:
        result = detect_infrastructure(changed_files=["Dockerfile"])
        assert len(result["findings"]) == 1
        assert result["highest_risk"] == "high"

    def test_highest_risk_is_critical_when_mixed(self) -> None:
        result = detect_infrastructure(
            changed_files=[".github/workflows/ci.yml", "Dockerfile", "src/app.py"]
        )
        assert result["highest_risk"] == "critical"
        assert len(result["findings"]) == 2

    def test_no_findings_for_safe_files(self) -> None:
        result = detect_infrastructure(changed_files=["src/app.py", "docs/readme.md"])
        assert result["findings"] == []
        assert result["highest_risk"] == "none"

    def test_file_count_reflects_input(self) -> None:
        result = detect_infrastructure(changed_files=["a.py", "b.py", "c.py"])
        assert result["file_count"] == 3
