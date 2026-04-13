#!/usr/bin/env python3
"""Tests for detect_infrastructure module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/security-detection/detect_infrastructure.py")
matches_pattern = mod.matches_pattern
get_security_risk_level = mod.get_security_risk_level
detect_infrastructure = mod.detect_infrastructure
CRITICAL_PATTERNS = mod.CRITICAL_PATTERNS
HIGH_PATTERNS = mod.HIGH_PATTERNS
main = mod.main


class TestMatchesPattern:
    """Tests for matches_pattern function."""

    def test_matches_workflow_file(self) -> None:
        assert matches_pattern(".github/workflows/ci.yml", CRITICAL_PATTERNS) is True

    def test_matches_auth_directory(self) -> None:
        assert matches_pattern("src/Auth/login.cs", CRITICAL_PATTERNS) is True

    def test_no_match_for_regular_file(self) -> None:
        assert matches_pattern("src/utils/helper.py", CRITICAL_PATTERNS) is False
        assert matches_pattern("src/utils/helper.py", HIGH_PATTERNS) is False

    def test_matches_env_file(self) -> None:
        assert matches_pattern(".env.production", CRITICAL_PATTERNS) is True

    def test_matches_dockerfile(self) -> None:
        assert matches_pattern("Dockerfile", HIGH_PATTERNS) is True

    def test_matches_terraform(self) -> None:
        assert matches_pattern("infra/main.tf", HIGH_PATTERNS) is True


class TestGetSecurityRiskLevel:
    """Tests for get_security_risk_level function."""

    def test_critical_for_workflow(self) -> None:
        assert get_security_risk_level(".github/workflows/deploy.yml") == "critical"

    def test_critical_for_auth(self) -> None:
        assert get_security_risk_level("src/Auth/TokenService.cs") == "critical"

    def test_high_for_dockerfile(self) -> None:
        assert get_security_risk_level("Dockerfile") == "high"

    def test_high_for_build_script(self) -> None:
        assert get_security_risk_level("build/deploy.sh") == "high"

    def test_none_for_regular_file(self) -> None:
        assert get_security_risk_level("src/models/user.py") == "none"

    def test_normalizes_backslashes(self) -> None:
        assert get_security_risk_level("src\\Auth\\login.cs") == "critical"

    def test_critical_for_secret_file(self) -> None:
        assert get_security_risk_level("config/secret.json") == "critical"

    def test_critical_for_pem_file(self) -> None:
        assert get_security_risk_level("certs/server.pem") == "critical"

    def test_high_for_config_json(self) -> None:
        assert get_security_risk_level("config/database.json") == "high"

    def test_critical_for_githooks(self) -> None:
        assert get_security_risk_level(".githooks/pre-commit") == "critical"


class TestDetectInfrastructure:
    """Tests for detect_infrastructure function."""

    def test_empty_files_returns_no_findings(self) -> None:
        result = detect_infrastructure(changed_files=[])
        assert result["findings"] == []
        assert result["highest_risk"] == "none"

    def test_none_files_returns_no_findings(self) -> None:
        result = detect_infrastructure(changed_files=None)
        assert result["findings"] == []

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


class TestMain:
    """Tests for main entry point."""

    def test_returns_zero_with_no_files(self, capsys: pytest.CaptureFixture) -> None:
        with patch("sys.argv", ["detect_infrastructure.py"]):
            result = main()
        assert result == 0

    def test_json_output(self, capsys: pytest.CaptureFixture) -> None:
        argv = [
            "detect_infrastructure.py", "--files",
            ".github/workflows/ci.yml", "--json",
        ]
        with patch("sys.argv", argv):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert '"critical"' in captured.out

    def test_human_output_for_findings(self, capsys: pytest.CaptureFixture) -> None:
        with patch("sys.argv", ["detect_infrastructure.py", "--files", ".github/workflows/ci.yml"]):
            result = main()
        assert result == 0
        captured = capsys.readouterr()
        assert "CRITICAL" in captured.out
