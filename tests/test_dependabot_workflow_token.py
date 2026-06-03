"""Regression test for #2307.

Dependabot PRs do NOT receive org/repo secrets by default, so
`secrets.GH_ACTIONS_PR_WRITE` resolves to an empty string in the
fetch-metadata step's context. The action then errors with:

    github-token is not set! Please add 'github-token:
    "${{ secrets.GITHUB_TOKEN }}"' to your workflow file.

Evidence: https://github.com/rjmurillo/ai-agents/actions/runs/26853238605/job/79190113142

This test asserts the read-only `dependabot/fetch-metadata` step uses
`secrets.GITHUB_TOKEN` (always available in the workflow context),
while the subsequent approval/merge steps may still use the PAT.
"""

from __future__ import annotations

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
    """Negative: fetch-metadata must NOT use GH_ACTIONS_PR_WRITE.

    That secret is empty in Dependabot PR contexts and triggers the
    'github-token is not set!' failure mode from #2307.
    """
    step = _fetch_metadata_step(workflow)
    token = _step_mapping(step, "with").get("github-token", "")
    assert "GH_ACTIONS_PR_WRITE" not in token, (
        "fetch-metadata must not depend on GH_ACTIONS_PR_WRITE; it is "
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


def test_approve_and_merge_steps_still_use_pat(workflow: dict) -> None:
    """Edge: write actions still require the PAT for ruleset compliance.

    The auto-approve and auto-merge steps must continue to use
    GH_ACTIONS_PR_WRITE so reviews come from a real user identity that
    satisfies branch-protection ruleset requirements.
    """
    job = workflow["jobs"]["dependabot"]
    write_steps = [
        s for s in job["steps"] if s.get("name") in {"Approve PR", "Enable auto-merge for non-major updates"}
    ]
    assert len(write_steps) == 2, "expected Approve PR + Enable auto-merge steps"
    for step in write_steps:
        gh_token = _step_mapping(step, "env").get("GH_TOKEN", "")
        assert "GH_ACTIONS_PR_WRITE" in gh_token, (
            f"{step['name']!r} must use GH_ACTIONS_PR_WRITE PAT for "
            f"ruleset-compliant reviews; got: {gh_token!r}"
        )
