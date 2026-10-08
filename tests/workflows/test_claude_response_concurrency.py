"""Pins the claude.yml concurrency group that ADR-114 relies on.

`claude-response` runs in `agent-claude`, which requires a reviewer, so every
authorized event waits for a click. Without a group, waiting runs pile up. The
group sits on the job, after `check-authorization`, so an event that fails
authorization skips the job by its `if:` (inferred, not observed).

A comment or review is a person's request, so it is keyed on its own id and is
never replaced. Push, label, assign, and issue events share one key per issue
or pull request. `cancel-in-progress` is false: GitHub keeps one running and
one pending job per group and a newer pending job replaces the older one
(docs.github.com, "Control the concurrency of workflows and jobs"), so the
thread queue stays short without cutting off a Claude run that is already
working.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "claude.yml"
# Each branch of the group expression, in evaluation order.
BRANCHES = (
    "github.event.comment.id && format('comment-{0}', github.event.comment.id)",
    "github.event.review.id && format('review-{0}', github.event.review.id)",
    "format('thread-{0}', github.event.issue.number"
    " || github.event.pull_request.number || github.run_id)",
)


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def group(workflow: dict[str, Any]) -> str:
    return workflow["jobs"]["claude-response"]["concurrency"]["group"]


def test_the_workflow_has_no_run_level_group(workflow: dict[str, Any]) -> None:
    """A run-level group would let a bot comment cancel an authorized run."""
    assert "concurrency" not in workflow


def test_check_authorization_is_outside_the_group(workflow: dict[str, Any]) -> None:
    assert "concurrency" not in workflow["jobs"]["check-authorization"]


def test_claude_response_never_cancels_running_work(workflow: dict[str, Any]) -> None:
    concurrency = workflow["jobs"]["claude-response"]["concurrency"]
    assert concurrency["cancel-in-progress"] is False


def test_the_group_is_one_expression_with_a_fixed_prefix(group: str) -> None:
    assert group.startswith("claude-response-${{ ")
    assert group.endswith(" }}")
    assert group.count("${{") == 1


def test_the_branches_appear_in_evaluation_order(group: str) -> None:
    positions = [group.index(branch) for branch in BRANCHES]
    assert positions == sorted(positions), "comment, then review, then the thread fallback"


@pytest.mark.parametrize("branch", BRANCHES)
def test_each_branch_is_present(group: str, branch: str) -> None:
    """Negative control: dropping a branch would merge distinct requests or threads."""
    assert branch in group


@pytest.mark.parametrize("prefix", ["'comment-{0}'", "'review-{0}'", "'thread-{0}'"])
def test_each_key_family_has_its_own_prefix(group: str, prefix: str) -> None:
    """A comment id and an issue number can be equal; the prefix keeps them apart."""
    assert group.count(prefix) == 1


def test_the_job_declares_its_authorization_gate(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["claude-response"]
    assert job["needs"] == "check-authorization"
    assert "authorized == 'true'" in job["if"]
