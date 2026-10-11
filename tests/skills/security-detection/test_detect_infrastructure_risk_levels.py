#!/usr/bin/env python3
"""Tests for get_security_risk_level, including lefthook config paths."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = str(Path(__file__).resolve().parent)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from detect_infrastructure_test_helpers import get_security_risk_level


class TestGetSecurityRiskLevel:
    """Tests for get_security_risk_level function."""

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            pytest.param(".github/workflows/deploy.yml", "critical", id="workflow"),
            pytest.param("src/Auth/TokenService.cs", "critical", id="auth"),
            pytest.param("Dockerfile", "high", id="dockerfile"),
            pytest.param("build/deploy.sh", "high", id="build-script"),
            pytest.param("src/models/user.py", "none", id="regular-file"),
            pytest.param("src\\Auth\\login.cs", "critical", id="normalizes-backslashes"),
            pytest.param("config/secret.json", "critical", id="secret-file"),
            pytest.param(".env.production", "critical", id="env-file"),
            pytest.param("infra/main.tf", "high", id="terraform"),
            pytest.param("certs/server.pem", "critical", id="pem-file"),
            pytest.param("config/database.json", "high", id="config-json"),
            pytest.param(
                "scripts/validation/git_hook_policy.py", "critical", id="git-hook-policy"
            ),
            pytest.param("scripts/validation/pre_pr.py", "none", id="pre-pr-not-policy"),
            pytest.param(".githooks/pre-commit", "none", id="githooks-not-policy"),
        ],
    )
    def test_risk_level_for_path(self, path: str, expected: str) -> None:
        assert get_security_risk_level(path) == expected


class TestLefthookRiskLevel:
    """Lefthook auto-discovered configs are critical; lookalikes are not."""

    @pytest.mark.parametrize(
        "config_path",
        [
            f"{base}{suffix}{extension}"
            for base in ("lefthook", ".lefthook", ".config/lefthook")
            for suffix in ("", "-local")
            for extension in (".yml", ".yaml", ".json", ".jsonc", ".toml")
        ],
    )
    def test_auto_discovered_lefthook_configs_are_critical(
        self, config_path: str
    ) -> None:
        assert get_security_risk_level(config_path) == "critical"

    @pytest.mark.parametrize(
        "config_path",
        [
            "config/lefthook.yml",
            "nested/lefthook.yml",
            "nested/.config/lefthook-local.jsonc",
        ],
    )
    def test_non_discovered_lefthook_lookalikes_are_not_critical(
        self, config_path: str
    ) -> None:
        assert get_security_risk_level(config_path) != "critical"
