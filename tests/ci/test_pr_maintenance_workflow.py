"""Wiring tests for .github/workflows/pr-maintenance.yml after process-prs was deleted.

The workflow keeps two read-only jobs: ``discover-prs`` lists the PRs that need
attention and reports orphan commits, and ``summarize`` writes the final summary.
The agent-gated ``process-prs`` job is gone, so no job writes to a PR or branch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pr-maintenance.yml"
WRITE_LEVELS = {"write", "write-all"}


@pytest.fixture(scope="module")
def workflow() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_the_workflow_keeps_exactly_the_two_read_only_jobs(workflow: dict[Any, Any]) -> None:
    assert set(workflow["jobs"]) == {"discover-prs", "summarize"}
    assert workflow["jobs"]["summarize"]["needs"] == "discover-prs"


def test_no_job_declares_an_environment(workflow: dict[Any, Any]) -> None:
    for name, job in workflow["jobs"].items():
        assert "environment" not in job, name


def test_no_job_holds_a_write_scope(workflow: dict[Any, Any]) -> None:
    """Negative: with process-prs gone, nothing pushes merge commits or comments on PRs."""
    assert workflow["permissions"] == {"contents": "read"}
    for name, job in workflow["jobs"].items():
        assert not WRITE_LEVELS & set(job["permissions"].values()), name


def test_discover_prs_token_can_read_the_status_rollup(workflow: dict[Any, Any]) -> None:
    """The discovery query reads statusCheckRollup, so github.token needs checks and statuses."""
    assert workflow["jobs"]["discover-prs"]["permissions"] == {
        "checks": "read",
        "contents": "read",
        "pull-requests": "read",
        "statuses": "read",
    }


def test_dispatch_offers_only_inputs_a_job_reads(workflow: dict[Any, Any]) -> None:
    """Negative: process_conflicts had no reader once process-prs was deleted."""
    triggers: dict[str, Any] = workflow[True] if True in workflow else workflow["on"]

    assert set(triggers["workflow_dispatch"]["inputs"]) == {"max_prs"}
    assert "process_conflicts" not in WORKFLOW.read_text(encoding="utf-8")
