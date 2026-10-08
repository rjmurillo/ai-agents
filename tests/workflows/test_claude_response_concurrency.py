"""Pins the claude.yml concurrency group that ADR-114 relies on.

`claude-response` runs in `agent-claude`, which requires a reviewer, so every
authorized event waits for a click. Without a group, waiting runs pile up. The
group sits on the job, after `check-authorization`, so an unauthorized or bot
event never enters it. `cancel-in-progress` is false: GitHub keeps one running
and one pending job per group and a newer pending job replaces the older one
(docs.github.com, "Control the concurrency of workflows and jobs"), so the
queue stays short without cutting off a Claude run that is already working.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "claude.yml"
GROUP_KEYS = (
    "github.event.issue.number",
    "github.event.pull_request.number",
    "github.run_id",
)


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_the_workflow_has_no_run_level_group(workflow: dict[str, Any]) -> None:
    """A run-level group would let a bot comment cancel an authorized run."""
    assert "concurrency" not in workflow


def test_check_authorization_is_outside_the_group(workflow: dict[str, Any]) -> None:
    assert "concurrency" not in workflow["jobs"]["check-authorization"]


def test_claude_response_never_cancels_running_work(workflow: dict[str, Any]) -> None:
    concurrency = workflow["jobs"]["claude-response"]["concurrency"]
    assert concurrency["cancel-in-progress"] is False


def test_the_group_is_keyed_per_issue_or_pull_request(workflow: dict[str, Any]) -> None:
    group = workflow["jobs"]["claude-response"]["concurrency"]["group"]
    assert group.startswith("claude-response-")
    positions = [group.index(key) for key in GROUP_KEYS]
    assert positions == sorted(positions), "issue, then pull request, then the run id fallback"


@pytest.mark.parametrize("key", GROUP_KEYS)
def test_each_key_is_present(workflow: dict[str, Any], key: str) -> None:
    """Negative control: dropping a key would merge unrelated threads or dispatches."""
    assert key in workflow["jobs"]["claude-response"]["concurrency"]["group"]


def test_the_group_waits_on_authorization(workflow: dict[str, Any]) -> None:
    job = workflow["jobs"]["claude-response"]
    assert job["needs"] == "check-authorization"
    assert "authorized == 'true'" in job["if"]
