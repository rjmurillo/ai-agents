"""Guards renovate.json settings that keep transitive lockfile pins fresh (#6028).

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
    assert schedule, "schedule must be non-empty so refreshes are weekly, not ad hoc"


def test_lock_file_maintenance_does_not_set_automerge(config: dict[str, Any]) -> None:
    assert "automerge" not in config["lockFileMaintenance"]


def test_vulnerability_alerts_enabled(config: dict[str, Any]) -> None:
    assert config["vulnerabilityAlerts"]["enabled"] is True


def test_vulnerability_alerts_bypass_minimum_release_age(config: dict[str, Any]) -> None:
    alerts = config["vulnerabilityAlerts"]
    assert "minimumReleaseAge" in alerts
    assert alerts["minimumReleaseAge"] is None


def test_vulnerability_alerts_do_not_set_automerge(config: dict[str, Any]) -> None:
    assert "automerge" not in config["vulnerabilityAlerts"]


def test_package_rules_keep_minimum_release_age(config: dict[str, Any]) -> None:
    ages = [r.get("minimumReleaseAge") for r in config["packageRules"]]
    assert "7 days" in ages


def test_still_extends_recommended_preset(config: dict[str, Any]) -> None:
    assert "config:recommended" in config["extends"]
