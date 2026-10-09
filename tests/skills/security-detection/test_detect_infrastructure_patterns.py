#!/usr/bin/env python3
"""Tests for matches_pattern."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from detect_infrastructure_test_helpers import CRITICAL_PATTERNS, HIGH_PATTERNS, matches_pattern


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
