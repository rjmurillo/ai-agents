"""Trigger and trust-gate tests for the CLI smoke workflow.

The workflow triggers on ``pull_request``, so a fork PR must fail closed with a
message naming the fork (REQ-047 AC12). The path filter script runs from the
base commit. Secrets, the Codex job, the result job, and trusted-script hygiene
live in the ``test_cli_smoke_trust_*`` siblings. Shared helpers live in
``tests/lib/cli_smoke_workflow.py`` and ``tests/lib/cli_smoke_fixtures.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.lib.cli_smoke_workflow import (
    _step_by_name,
)

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]


def _triggers(workflow_doc: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML parses the bare key `on` as boolean True.
    triggers = workflow_doc.get(True) or workflow_doc.get("on")
    assert isinstance(triggers, dict), "workflow has no `on` mapping"
    return triggers


def test_workflow_triggers_on_pull_request_and_dispatch_only(
    workflow_doc: dict[Any, Any],
) -> None:
    """Positive and negative: the nightly schedule is gone, no privileged trigger exists."""
    triggers = _triggers(workflow_doc)

    assert set(triggers) == {"pull_request", "workflow_dispatch"}
    assert set(triggers["pull_request"]["types"]) == {
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
    }
    assert "pull_request_target" not in triggers
    assert "schedule" not in triggers


def test_runs_are_cancelled_per_pull_request(workflow_doc: dict[Any, Any]) -> None:
    concurrency = workflow_doc["concurrency"]

    assert concurrency["cancel-in-progress"] is True
    assert "github.event.pull_request.number" in concurrency["group"]


def test_top_level_permissions_are_read_only(workflow_doc: dict[Any, Any]) -> None:
    assert workflow_doc["permissions"] == {"contents": "read"}
    for name, job in workflow_doc["jobs"].items():
        assert job["permissions"] == {"contents": "read"}, name


def test_trust_gate_receives_the_head_repository(workflow_doc: dict[Any, Any]) -> None:
    """Positive: a fork PR is told apart from a same-repo PR by its head repository."""
    gate = _step_by_name(workflow_doc["jobs"]["authorize"], "Check trusted context")

    assert gate["env"]["HEAD_REPOSITORY"] == "${{ github.event.pull_request.head.repo.full_name }}"
    assert '--head-repository "$HEAD_REPOSITORY"' in gate["run"]
    assert "assert_trusted_smoke_context.py" in gate["run"]


@pytest.mark.parametrize("job_name", ["smoke", "smoke-codex"])
def test_legs_wait_for_the_filter_and_the_trust_gate(
    workflow_doc: dict[Any, Any], job_name: str
) -> None:
    """Negative: no leg can start without a positive path decision and a trusted context."""
    job = workflow_doc["jobs"][job_name]

    assert set(job["needs"]) == {"changes", "authorize"}
    assert "needs.changes.outputs.run == 'true'" in job["if"]
    assert "needs.authorize.outputs.trusted == 'true'" in job["if"]


def test_path_filter_diffs_with_full_history_through_the_python_cli(
    workflow_doc: dict[Any, Any],
) -> None:
    job = workflow_doc["jobs"]["changes"]
    checkout = next(step for step in job["steps"] if "actions/checkout" in step.get("uses", ""))
    filter_step = _step_by_name(job, "Decide whether the smoke must run")

    assert checkout["with"]["fetch-depth"] == 0
    assert "scripts/validation/cli_smoke_paths.py" in filter_step["run"]
    assert filter_step["env"]["BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    assert filter_step["env"]["HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    assert job["outputs"]["run"] == "${{ steps.filter.outputs.run }}"
