"""Guards Renovate automerge for workflow files and the CLI smoke pins.

#6506 review-gates-15 made bumps to ``.github/workflows/**`` and
``.github/cli-smoke/**`` wait for a human approval. Richard removed that gate on
2026-11-23 (PR #7521): CI is the gate, so these updates automerge like the rest.
The shared glob constants live in ``tests/test_renovate_config.py``.
"""

from __future__ import annotations

import json
from fnmatch import fnmatch
from typing import Any

import pytest

from tests.test_renovate_config import (
    _CLI_SMOKE_FILE_GLOB,
    _EXEMPT_FILE_GLOBS,
    _WORKFLOW_FILE_GLOB,
    CONFIG_PATH,
)


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_vulnerability_alerts_do_not_force_automerge(config: dict[str, Any]) -> None:
    """Renovate appends each alert as a rule that carries `force: {vulnerabilityAlerts}`.

    A forced key there beats every user packageRules entry. Leaving it out keeps
    alert PRs on the repo default (`automerge: true`) and under the same rules as
    every other update.
    """
    assert "automerge" not in config["vulnerabilityAlerts"]
    assert config["automerge"] is True


def test_workflow_file_updates_automerge(config: dict[str, Any]) -> None:
    """A bump to .github/workflows/** or .github/cli-smoke/** automerges (PR #7521).

    The rule must stay unnarrowed. A `matchUpdateTypes` or `matchManagers` key
    would leave some workflow bumps on whatever an earlier rule decided.
    """
    rules = config["packageRules"]
    matches = [
        i for i, rule in enumerate(rules) if rule.get("matchFileNames") == _EXEMPT_FILE_GLOBS
    ]
    assert matches, "no packageRules entry targets the workflow file globs"
    rule = rules[matches[-1]]
    assert rule["automerge"] is True
    extra = set(rule) - {"matchFileNames", "description", "automerge"}
    assert not extra, f"the workflow rule is narrowed by {sorted(extra)}"
    later_off = [r for r in rules[matches[-1] + 1 :] if r.get("automerge") is False]
    assert not later_off, f"a later rule turns automerge off: {later_off}"


def test_no_regex_custom_manager_remains(config: dict[str, Any]) -> None:
    """The CLI pins moved to .github/cli-smoke/*/package.json, which the npm manager reads."""
    assert "customManagers" not in config


def test_exemption_globs_cover_workflow_and_lockfile_paths() -> None:
    """Edge: the globs match a workflow, a CLI manifest, and a CLI lockfile.

    This test pins that the lockfile paths stay under the globs. It cannot show
    Renovate's behavior itself.
    """
    paths = [
        ".github/workflows/ci.yml",
        ".github/cli-smoke/claude/package.json",
        ".github/cli-smoke/pi/package-lock.json",
    ]
    for path in paths:
        assert any(fnmatch(path, glob) for glob in _EXEMPT_FILE_GLOBS), path
    assert not fnmatch("src/app/package-lock.json", _CLI_SMOKE_FILE_GLOB)
    assert not fnmatch("src/ci.yml", _WORKFLOW_FILE_GLOB)


def test_cli_smoke_lock_maintenance_rides_the_shared_branch(config: dict[str, Any]) -> None:
    """The cli-smoke lock refresh automerges on the shared branch (PR #7521).

    Renovate puts every lockFileMaintenance update on ``renovate/lock-file-maintenance``
    and automerges a branch only when every update in it allows it. With every
    refresh allowed, the separate branch topic is no longer needed.
    """
    rules = config["packageRules"]
    matches = [
        index
        for index, rule in enumerate(rules)
        if rule.get("matchUpdateTypes") == ["lockFileMaintenance"]
    ]
    assert len(matches) == 1, "expected exactly one lockFileMaintenance packageRules entry"
    rule = rules[matches[0]]
    assert rule["matchFileNames"] == [_CLI_SMOKE_FILE_GLOB]
    assert rule["automerge"] is True
    assert "branchTopic" not in rule
    assert config["lockFileMaintenance"]["automerge"] is True
