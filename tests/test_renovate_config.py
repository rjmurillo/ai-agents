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

# Automerge is the default for every manager, with one deliberate exception:
# a devcontainer feature or image bump must refresh devcontainer-lock.json in
# the same commit. Renovate's devcontainer manager does not rewrite that lock
# file, so an automerged bump would leave the committed digests stale and break
# the documented `devcontainer up --frozen-lockfile` path. The exemption is
# listed here so that widening it takes a deliberate edit, and
# `test_devcontainer_updates_require_a_manual_merge` asserts it is still there.
_AUTOMERGE_OFF_MANAGERS = {"devcontainer"}

# The second deliberate exception is by path, not manager (#6506 review-gates-15):
# a workflow file can hold secrets or write tokens, so a bump to it needs a human
# approval. Scope stays on the workflow directory because PR #6127 made automerge
# universal and a wider glob would quietly remove other updates from that path.
_WORKFLOW_FILE_GLOB = ".github/workflows/**"
_AUTOMERGE_OFF_FILE_GLOBS = {_WORKFLOW_FILE_GLOB}


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


def test_automerge_stays_on_except_for_named_managers(config: dict[str, Any]) -> None:
    """A rule may disable automerge only for a manager in _AUTOMERGE_OFF_MANAGERS.

    Automerge is the repo default. A rule that turns it off for anything else
    is almost certainly a mistake, so it fails here instead of quietly
    removing every future update from the auto-merge path.
    """
    for rule in config["packageRules"]:
        if rule.get("automerge") is False:
            if set(rule.get("matchFileNames", [])) and not rule.get("matchManagers"):
                assert set(rule["matchFileNames"]) <= _AUTOMERGE_OFF_FILE_GLOBS, (
                    f"rule {rule.get('description', rule)!r} disables automerge for "
                    f"{rule['matchFileNames']}; add the glob to _AUTOMERGE_OFF_FILE_GLOBS "
                    "if that is intended"
                )
                continue
            managers = set(rule.get("matchManagers", []))
            assert managers <= _AUTOMERGE_OFF_MANAGERS, (
                f"rule {rule.get('description', rule)!r} disables automerge for "
                f"{sorted(managers - _AUTOMERGE_OFF_MANAGERS)}; add the manager to "
                "_AUTOMERGE_OFF_MANAGERS if that is intended"
            )
            assert managers, "an automerge:false rule must name the managers it covers"


def test_devcontainer_updates_require_a_manual_merge(config: dict[str, Any]) -> None:
    """The lock refresh must ship with the bump, so this exemption must exist.

    Without this rule a Renovate feature bump automerges on its own and leaves
    devcontainer-lock.json holding digests for refs that are no longer used,
    which breaks `devcontainer up --frozen-lockfile` for every contributor.

    Renovate applies packageRules in order with later rules winning, so the
    requirement only holds while no rule after the exemption turns automerge
    back on. That is why this test pins position and not just presence: a later
    rule carrying `automerge: true` reaches devcontainer too, whether it is
    unscoped, narrowed by `matchUpdateTypes`, or narrowed by `matchDatasources`
    such as `docker`, none of which exclude the manager. A later `automerge:
    false` rule is allowed, since it can only keep updates reviewable.
    """
    rules = config["packageRules"]
    exemptions = [
        index
        for index, rule in enumerate(rules)
        if "devcontainer" in rule.get("matchManagers", []) and rule.get("automerge") is False
    ]
    assert exemptions, "no packageRules entry disables automerge for the devcontainer manager"
    exemption = rules[exemptions[-1]]
    # The exemption must cover every devcontainer update. Narrow it with a
    # matchUpdateTypes or matchDatasources key and an earlier automerge:true
    # rule takes over for the rest, silently, with this test still green.
    extra = set(exemption) - {"matchManagers", "description", "automerge"}
    assert not extra, f"the devcontainer exemption is narrowed by {sorted(extra)}"
    reenabled = [rule for rule in rules[exemptions[-1] + 1 :] if rule.get("automerge") is True]
    assert not reenabled, (
        "a rule after the devcontainer exemption re-enables automerge, which would "
        f"land a bump without the lock refresh: {reenabled}"
    )


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


def _workflow_exemptions(config: dict[str, Any]) -> list[int]:
    return [
        index
        for index, rule in enumerate(config["packageRules"])
        if rule.get("matchFileNames") == [_WORKFLOW_FILE_GLOB] and rule.get("automerge") is False
    ]


def test_workflow_file_updates_require_a_manual_merge(config: dict[str, Any]) -> None:
    """A bump to .github/workflows/** must not automerge (#6506 review-gates-15).

    Like the devcontainer exemption, this holds only while no later rule turns
    automerge back on, and only while the rule carries no narrowing key. A
    `matchUpdateTypes` or `matchManagers` key would leave some workflow bumps on
    the automerge path with this test still green.
    """
    rules = config["packageRules"]
    exemptions = _workflow_exemptions(config)
    assert exemptions, "no packageRules entry disables automerge for .github/workflows/**"
    exemption = rules[exemptions[-1]]
    extra = set(exemption) - {"matchFileNames", "description", "automerge"}
    assert not extra, f"the workflow exemption is narrowed by {sorted(extra)}"
    reenabled = [rule for rule in rules[exemptions[-1] + 1 :] if rule.get("automerge") is True]
    assert not reenabled, f"a rule after the workflow exemption re-enables automerge: {reenabled}"


def test_workflow_exemption_does_not_reach_other_paths(config: dict[str, Any]) -> None:
    """Edge: the exception names the workflow directory and nothing wider."""
    for rule in config["packageRules"]:
        if rule.get("automerge") is False and "matchFileNames" in rule:
            assert rule["matchFileNames"] == [_WORKFLOW_FILE_GLOB]
    assert config["automerge"] is True, "the repo default stays automerge"


def test_workflow_exemption_follows_the_rules_that_enable_automerge(
    config: dict[str, Any],
) -> None:
    """Edge: Renovate applies rules in order, so every automerge:true rule must come first."""
    rules = config["packageRules"]
    index = _workflow_exemptions(config)[-1]
    enabling = [i for i, rule in enumerate(rules) if rule.get("automerge") is True]
    assert enabling, "expected at least one rule that enables automerge"
    assert max(enabling) < index


def test_no_regex_custom_manager_remains(config: dict[str, Any]) -> None:
    """The CLI pins moved to .github/cli-smoke/*/package.json, which the npm manager reads."""
    assert "customManagers" not in config
