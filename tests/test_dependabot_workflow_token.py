"""Regression tests for the Dependabot auto-merge workflow.

#2307: Dependabot PRs do not receive repo secrets, so a stored secret resolves
to an empty string and `dependabot/fetch-metadata` fails with
"github-token is not set!". The fetch-metadata step must use
`secrets.GITHUB_TOKEN`.

The workflow holds a write token under `pull_request_target`, so it must read
no stored secret, declare no environment, and gate on the PR author (CWE-441).
Renovate merges through its own platform auto-merge, so no job here serves it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "dependabot-approve-and-auto-merge.yml"
)


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def _step_string(step: dict, key: str) -> str:
    value = step.get(key)
    return value if isinstance(value, str) else ""


def _step_mapping(step: dict, key: str) -> dict:
    value = step.get(key)
    return value if isinstance(value, dict) else {}


def _fetch_metadata_step(workflow: dict) -> dict:
    job = workflow["jobs"]["dependabot"]
    for step in job["steps"]:
        uses = _step_string(step, "uses")
        if uses.startswith("dependabot/fetch-metadata@"):
            return step
    raise AssertionError("dependabot/fetch-metadata step not found")


def test_fetch_metadata_uses_github_token(workflow: dict) -> None:
    """Positive: fetch-metadata is wired to secrets.GITHUB_TOKEN."""
    step = _fetch_metadata_step(workflow)
    token = _step_mapping(step, "with").get("github-token", "")
    assert token == "${{ secrets.GITHUB_TOKEN }}", (
        f"fetch-metadata must use secrets.GITHUB_TOKEN (always available "
        f"in Dependabot PR context), got: {token!r}. See #2307."
    )


def test_fetch_metadata_does_not_use_pr_write_pat(workflow: dict) -> None:
    """Negative: fetch-metadata must NOT use the BOT_PAT secret.

    Org/repo secrets are empty in Dependabot PR contexts and trigger the
    'github-token is not set!' failure mode from #2307. fetch-metadata must
    stay on GITHUB_TOKEN.
    """
    step = _fetch_metadata_step(workflow)
    token = _step_mapping(step, "with").get("github-token", "")
    assert "BOT_PAT" not in token, (
        "fetch-metadata must not depend on BOT_PAT; org/repo secrets are "
        "empty in Dependabot PR contexts. See #2307."
    )


def test_yaml_null_fields_do_not_break_token_checks() -> None:
    """Edge: explicit YAML nulls are treated like missing optional fields."""
    workflow = {
        "jobs": {
            "dependabot": {
                "steps": [
                    {"uses": None, "with": None, "env": None},
                    {
                        "uses": "dependabot/fetch-metadata@"
                        "08eff52bf64351f401fb50d4972fa95b9f2c2d1b",
                        "with": {"github-token": "${{ secrets.GITHUB_TOKEN }}"},
                    },
                ]
            }
        }
    }

    step = _fetch_metadata_step(workflow)
    token = _step_mapping(step, "with").get("github-token", "")

    assert token == "${{ secrets.GITHUB_TOKEN }}"


def _text() -> str:
    return WORKFLOW.read_text()


def test_workflow_text_has_no_bot_pat() -> None:
    """Negative: BOT_PAT is unprovisioned and must not appear anywhere."""
    assert "BOT_PAT" not in _text()


def test_no_job_declares_an_environment(workflow: dict) -> None:
    """Negative: no job pulls in environment-scoped secrets."""
    with_env = [name for name, job in workflow["jobs"].items() if "environment" in job]
    assert with_env == []


def test_no_renovate_job(workflow: dict) -> None:
    """Negative: Renovate merges through platform auto-merge, not this file."""
    assert "renovate" not in workflow["jobs"]


def test_no_approve_pr_step(workflow: dict) -> None:
    """Negative: the approval did nothing (required approvals are 0)."""
    names = [s.get("name") for job in workflow["jobs"].values() for s in job["steps"]]
    assert "Approve PR" not in names
    assert "gh pr review" not in _text()


def test_enable_auto_merge_uses_github_token(workflow: dict) -> None:
    """Positive: the merge step runs on the per-run token."""
    steps = {s.get("name"): s for s in workflow["jobs"]["dependabot"]["steps"]}
    token = _step_mapping(steps["Enable auto-merge"], "env").get("GH_TOKEN", "")
    assert token == "${{ secrets.GITHUB_TOKEN }}"


def test_job_if_gates_on_pr_author_and_head_repo(workflow: dict) -> None:
    """Positive: the gate reads PR author and head repo, never github.actor."""
    condition = workflow["jobs"]["dependabot"]["if"]
    assert "github.event.pull_request.user.login" in condition
    assert "github.event.pull_request.head.repo.full_name" in condition
    assert "github.actor" not in condition


def test_job_permissions_are_the_two_write_scopes(workflow: dict) -> None:
    """Positive: gh pr merge --auto needs contents and pull-requests write."""
    assert workflow["jobs"]["dependabot"]["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
    }


def test_only_github_token_secret_is_referenced() -> None:
    """Negative: GITHUB_TOKEN is the only secrets.* name in the file."""
    names = set(re.findall(r"secrets\.([A-Za-z_][A-Za-z0-9_]*)", _text()))
    assert names == {"GITHUB_TOKEN"}
