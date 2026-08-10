"""Pin the Trunk Merge Queue exemption in the semantic PR title check.

Trunk tests a queued pull request by opening a draft pull request whose title
is its own branch name, `trunk-merge/pr-<n>/<uuid>`. That can never satisfy a
conventional-commit title, so `Validate PR title` failed on every queued pull
request and removed it from the queue. Measured 2026-08-09 on PR #4747, whose
test pull request #4794 failed exactly this required check.

The exemption has two halves and both matter:

1. The validation steps skip for a `trunk-merge/` head branch.
2. The job itself still runs, so the required context reports.

A job-level `if:` would satisfy the first and break the second, leaving the
context unreported and the queue blocked on a check that never arrives, which
is the same deadlock that stalled `main` for five hours earlier that day.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "semantic-pr-title-check.yml"
)


@pytest.fixture(scope="module")
def job() -> dict:
    data = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return data["jobs"]["main"]


def test_required_context_name_is_unchanged(job: dict) -> None:
    """The job name is the required status check context; renaming it is a
    branch-protection change (`.claude/rules/ci-scripts.md` MUST 22)."""
    assert job["name"] == "Validate PR title"


def test_job_has_no_top_level_if(job: dict) -> None:
    """Negative control for the deadlock. A job-level `if:` leaves the required
    context unreported, which blocks every pull request rather than skipping."""
    assert "if" not in job


def test_skip_expression_covers_trunk_merge_branches(job: dict) -> None:
    expression = job["env"]["SKIP_TITLE_CHECK"]
    assert "startsWith(github.head_ref, 'trunk-merge/')" in expression


def test_skip_expression_still_covers_every_bot_actor(job: dict) -> None:
    """Edge: the exemption must add to the bot skips, never replace them."""
    expression = job["env"]["SKIP_TITLE_CHECK"]
    for actor in ("dependabot[bot]", "github-actions[bot]", "renovate[bot]"):
        assert f"github.actor == '{actor}'" in expression


def test_every_validating_step_is_gated_on_the_skip(job: dict) -> None:
    """Positive: each step that does real work honours the skip. A step added
    later without the guard would run against a trunk-merge title and fail."""
    validating = [s for s in job["steps"] if s.get("name") != "Skip for bot actors"]
    assert validating, "no validating steps found"
    for step in validating:
        assert step.get("if") == "env.SKIP_TITLE_CHECK != 'true'"


def test_notice_step_fires_only_when_skipping(job: dict) -> None:
    notice = [s for s in job["steps"] if s.get("name") == "Skip for bot actors"]
    assert len(notice) == 1
    assert notice[0].get("if") == "env.SKIP_TITLE_CHECK == 'true'"
