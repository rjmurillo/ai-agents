"""Tests for the Backlog Triage workflow human-approval handoff."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "backlog-triage.yml"


def _load_workflow() -> dict[str, Any]:
    with _WORKFLOW_PATH.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected {_WORKFLOW_PATH} to parse as a mapping")
    return loaded


def _step(job: dict[str, Any], name: str) -> dict[str, Any]:
    steps = job.get("steps")
    assert isinstance(steps, list)
    for step in steps:
        if isinstance(step, dict) and step.get("name") == name:
            return step
    raise AssertionError(f"missing step {name!r}")


def _workflow_dispatch(workflow: dict[str, Any]) -> dict[str, Any]:
    trigger = workflow.get("on") or workflow.get(True)
    assert isinstance(trigger, dict)
    dispatch = trigger.get("workflow_dispatch")
    assert isinstance(dispatch, dict)
    return dispatch


class TestRecommendationArtifacts:
    def test_recommendation_build_is_failure_isolated_until_upload(self) -> None:
        workflow = _load_workflow()
        recommend = workflow["jobs"]["recommend"]
        build = _step(recommend, "Build recommendation report and manifest")

        assert build["id"] == "recommend"
        assert build["continue-on-error"] is True

        fail = _step(recommend, "Fail on incomplete recommendation manifest")
        assert fail["if"] == "steps.recommend.outcome == 'failure'"


class TestApplyApprovalGate:
    def test_read_only_triage_jobs_skip_during_apply_dispatch(self) -> None:
        workflow = _load_workflow()
        discover = workflow["jobs"]["discover-issues"]

        assert discover["if"] == "github.event_name != 'workflow_dispatch' || !inputs.apply"

    def test_dispatch_input_carries_human_approved_manifest(self) -> None:
        workflow = _load_workflow()
        dispatch = _workflow_dispatch(workflow)
        inputs = dispatch["inputs"]

        assert "approved_manifest_json" in inputs

    def test_apply_job_uses_dispatch_manifest_not_same_run_artifact(self) -> None:
        workflow = _load_workflow()
        apply = workflow["jobs"]["apply"]

        assert "needs" not in apply
        with_names = [step.get("name") for step in apply["steps"] if isinstance(step, dict)]
        assert "Download approval manifest" not in with_names

        apply_step = _step(apply, "Apply approved manifest")
        assert "--manifest-env APPROVED_MANIFEST_JSON" in apply_step["run"]
