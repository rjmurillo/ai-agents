"""Guards renovate.json: fresh lockfile pins (#6028) and automerge of every update.

pip-audit went red on main because uv.lock held stale transitive pins
(pyjwt, urllib3) with known CVEs. config:recommended leaves
lockFileMaintenance off, so Renovate only bumped direct dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

CONFIG_PATH = Path(__file__).resolve().parents[1] / "renovate.json"


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_lock_file_maintenance_enabled(config: dict[str, Any]) -> None:
    lfm = config["lockFileMaintenance"]
    assert lfm["enabled"] is True


def test_lock_file_maintenance_has_schedule(config: dict[str, Any]) -> None:
    schedule = config["lockFileMaintenance"]["schedule"]
    assert isinstance(schedule, list)
    assert schedule == ["before 4am on monday"]


def test_lock_file_maintenance_automerges(config: dict[str, Any]) -> None:
    assert config["lockFileMaintenance"]["automerge"] is True


def test_vulnerability_alerts_enabled(config: dict[str, Any]) -> None:
    assert config["vulnerabilityAlerts"]["enabled"] is True


def test_vulnerability_alerts_bypass_minimum_release_age(config: dict[str, Any]) -> None:
    alerts = config["vulnerabilityAlerts"]
    assert "minimumReleaseAge" in alerts
    assert alerts["minimumReleaseAge"] is None


def test_vulnerability_alerts_label_security(config: dict[str, Any]) -> None:
    assert "security" in config["vulnerabilityAlerts"]["labels"]


def test_vulnerability_alerts_automerge(config: dict[str, Any]) -> None:
    assert config["vulnerabilityAlerts"]["automerge"] is True


def test_global_automerge_and_platform_automerge_enabled(config: dict[str, Any]) -> None:
    assert config["automerge"] is True
    assert config["platformAutomerge"] is True


def test_no_package_rule_disables_automerge(config: dict[str, Any]) -> None:
    for rule in config["packageRules"]:
        assert rule.get("automerge") is not False


def test_no_package_rule_excludes_packages_from_automerge(config: dict[str, Any]) -> None:
    for rule in config["packageRules"]:
        names = rule.get("matchPackageNames", [])
        assert not any(name.startswith("!") for name in names)


def test_cli_packages_keep_release_age_and_automerge(config: dict[str, Any]) -> None:
    rule = next(
        r
        for r in config["packageRules"]
        if "@anthropic-ai/claude-code" in r.get("matchPackageNames", [])
    )
    assert rule["automerge"] is True
    assert rule["minimumReleaseAge"] == "7 days"
    assert set(rule["matchUpdateTypes"]) == {"major", "minor", "patch"}


def test_major_updates_stay_labelled(config: dict[str, Any]) -> None:
    rule = next(r for r in config["packageRules"] if r.get("matchUpdateTypes") == ["major"])
    assert "renovate-major" in rule["addLabels"]
    assert rule.get("automerge") is not False


def test_package_rules_keep_minimum_release_age(config: dict[str, Any]) -> None:
    ages = [r.get("minimumReleaseAge") for r in config["packageRules"]]
    assert "7 days" in ages


def test_still_extends_recommended_preset(config: dict[str, Any]) -> None:
    assert "config:recommended" in config["extends"]
