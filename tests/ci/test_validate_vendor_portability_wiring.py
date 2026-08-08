"""Structural tests for validate-vendor-portability.yml CI wiring.

The portability ratchets inspect the whole repository tree, so every supported
event must run them. A per-change path filter can report success without
measuring the tree and leave main red (issue #4752).

Each test is a negative control: removing the structural property causes a test
failure before anything runs in CI.  Tests parse the YAML rather than
substring-searching raw text to avoid the 300-character window trap that let
commented-out YAML pass substring checks in issue #4041.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "validate-vendor-portability.yml"
)
_VALIDATOR_COMMANDS = (
    "python3 scripts/validation/check_vendor_portability.py",
    "python3 -m scripts.validation.check_skill_portability",
    "uv run --frozen python scripts/validation/check_skill_md_exec_portability.py",
    "uv run --frozen python scripts/validation/check_skill_md_portability.py",
    "python3 scripts/validation/check_skill_resolver_anchoring.py",
    "python3 scripts/validation/check_skill_contract_tests.py",
)


def _load_workflow() -> Any:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _validate_job_steps() -> Any:
    wf = _load_workflow()
    return wf["jobs"]["validate-portability"]["steps"]


@pytest.mark.parametrize("command", _VALIDATOR_COMMANDS)
def test_each_validator_runs_unconditionally(command: str) -> None:
    """Every validator command must run exactly once and propagate failures."""
    steps = _validate_job_steps()
    matches = [step for step in steps if step.get("run", "").strip() == command]
    assert len(matches) == 1, f"Expected one unconditional step for {command!r}"
    step = matches[0]
    assert "if" not in step, f"{command!r} must not be conditionally skipped"
    assert "continue-on-error" not in step, f"{command!r} must propagate failures"


def test_validation_job_is_unconditional() -> None:
    """Every push, pull request, and dispatch must execute the ratchets."""
    job = _load_workflow()["jobs"]["validate-portability"]
    assert "needs" not in job, "validation must not depend on a change-detector job"
    assert "if" not in job, "validation must not be gated by a path-filter result"


def test_path_filter_and_skip_jobs_are_absent() -> None:
    """A skip announcer must not manufacture success without a measurement."""
    jobs = _load_workflow()["jobs"]
    assert "check-changes" not in jobs
    assert "skip-validation" not in jobs
    assert all(
        "dorny/paths-filter@" not in step.get("uses", "")
        for job in jobs.values()
        for step in job.get("steps", [])
    )


def test_all_supported_events_run_the_workflow() -> None:
    """Push, pull-request, and manual runs must all reach validation."""
    triggers = _load_workflow()[True]
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["pull_request"]["branches"] == ["main"]
    assert "workflow_dispatch" in triggers


@pytest.mark.parametrize("event_name", ("push", "pull_request"))
def test_triggers_have_no_path_filters(event_name: str) -> None:
    """Event-level filters must not suppress a whole-tree measurement."""
    event = _load_workflow()[True][event_name]
    assert "paths" not in event
    assert "paths-ignore" not in event
