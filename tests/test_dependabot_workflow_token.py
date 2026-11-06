"""Regression tests for the Dependabot auto-merge workflow.

The workflow holds a write token under `pull_request_target`, so it must read
no stored secret, declare no environment, run no third-party action, check out
no PR code, and gate on the PR author (CWE-441).
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


EXPECTED_GATE = (
    "github.event.pull_request.user.login == 'dependabot[bot]' && "
    "github.event.pull_request.head.repo.full_name == github.repository"
)


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _step_mapping(step: dict, key: str) -> dict:
    value = step.get(key)
    return value if isinstance(value, dict) else {}


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


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


def test_job_if_is_exactly_the_author_and_head_repo_gate(workflow: dict) -> None:
    """Positive: an edit to || or != widens who reaches the write token."""
    assert workflow["jobs"]["dependabot"]["if"] == EXPECTED_GATE


def test_no_step_uses_an_action(workflow: dict) -> None:
    """Negative: no checkout and no third-party code runs with the write token."""
    used = [s["uses"] for job in workflow["jobs"].values() for s in job["steps"] if "uses" in s]
    assert used == []


def test_trigger_keeps_reopened(workflow: dict) -> None:
    """Positive: a reopened Dependabot PR gets auto-merge (owner decision 2026-11-05)."""
    # PyYAML reads the bare key `on` as the boolean True.
    types = workflow[True]["pull_request_target"]["types"]
    assert types == ["opened", "synchronize", "reopened"]


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


def _merge_step_run(workflow: dict) -> str:
    steps = {s.get("name"): s for s in workflow["jobs"]["dependabot"]["steps"]}
    return steps["Enable auto-merge"]["run"]


def test_workflow_file_prs_are_left_for_manual_merge(workflow: dict) -> None:
    """Positive: a PR touching .github/workflows/ returns before gh pr merge (review-gates-15)."""
    run = _merge_step_run(workflow)
    assert 'gh pr diff "$PR_URL" --name-only' in run
    assert "grep -q '^\\.github/workflows/'" in run
    assert run.index("exit 0") < run.index("gh pr merge --auto")


def test_file_list_is_read_before_any_decision(workflow: dict) -> None:
    """Edge: the file list is a plain assignment, so a failed read aborts under bash -e."""
    run = _merge_step_run(workflow)
    assert run.lstrip().startswith("files=$(gh pr diff")
    assert "|| true" not in run
    assert "continue-on-error" not in _text()


def test_auto_merge_still_enabled_for_other_prs(workflow: dict) -> None:
    """Positive: the merge command remains, scoped to the squash method."""
    assert 'gh pr merge --auto --squash "$PR_URL"' in _merge_step_run(workflow)
