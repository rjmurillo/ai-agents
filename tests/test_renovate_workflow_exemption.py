"""Guards the no-automerge exemption for workflow files and the CLI smoke pins.

#6506 review-gates-15: a workflow file can hold secrets or write tokens, so a bump to
it needs a human approval. The CLI smoke pins moved from the workflow into
``.github/cli-smoke/`` (workflow-ci-01), and those CLIs run beside the smoke
credentials, so they keep the same approval. The shared glob constants live in
``tests/test_renovate_config.py`` beside the manager exemption they extend.
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

    A forced `automerge: true` there beats every user packageRules entry, including
    the workflow-file exemption (#6506 review-gates-15). Leaving the key out keeps
    alert PRs on the repo default (`automerge: true`) and lets the exemption apply.
    """
    assert "automerge" not in config["vulnerabilityAlerts"]
    assert config["automerge"] is True


def _workflow_exemptions(config: dict[str, Any]) -> list[int]:
    return [
        index
        for index, rule in enumerate(config["packageRules"])
        if rule.get("matchFileNames") == _EXEMPT_FILE_GLOBS and rule.get("automerge") is False
    ]


def test_workflow_file_updates_require_a_manual_merge(config: dict[str, Any]) -> None:
    """A bump to .github/workflows/** or .github/cli-smoke/** must not automerge (#6506).

    Like the devcontainer exemption, this holds only while no later rule turns
    automerge back on, and only while the rule carries no narrowing key. A
    `matchUpdateTypes` or `matchManagers` key would leave some workflow bumps on
    the automerge path with this test still green.
    """
    rules = config["packageRules"]
    exemptions = _workflow_exemptions(config)
    assert exemptions, "no packageRules entry disables automerge for the workflow file globs"
    exemption = rules[exemptions[-1]]
    extra = set(exemption) - {"matchFileNames", "description", "automerge"}
    assert not extra, f"the workflow exemption is narrowed by {sorted(extra)}"
    reenabled = [rule for rule in rules[exemptions[-1] + 1 :] if rule.get("automerge") is True]
    assert not reenabled, f"a rule after the workflow exemption re-enables automerge: {reenabled}"


def test_workflow_exemption_does_not_reach_other_paths(config: dict[str, Any]) -> None:
    """Edge: the exception names the two directories and nothing wider."""
    for rule in config["packageRules"]:
        if rule.get("automerge") is False and "matchFileNames" in rule:
            assert rule["matchFileNames"] == _EXEMPT_FILE_GLOBS


def test_repo_default_stays_automerge(config: dict[str, Any]) -> None:
    assert config["automerge"] is True


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


def test_exemption_globs_cover_workflow_and_lockfile_paths() -> None:
    """Edge: the globs match a workflow, a CLI manifest, and a CLI lockfile.

    Renovate merges ``lockFileMaintenance`` config first and applies ``packageRules``
    afterwards (flatten.ts), so a ``matchFileNames`` rule reaches the weekly lockfile
    refresh. This test pins that the lockfile paths fall under the exempt globs.
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
