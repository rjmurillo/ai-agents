"""Contract tests for the changed-file ruff ratchet in pytest.yml (Issue #2939).

The repository carries a pre-existing backlog of ruff findings, so CI must
fail only on new violations in changed Python files. These tests pin the
ratchet contract so a later edit cannot silently restore a repo-wide
report-only run or drop the gating/skip condition.

Issue #4854: the ruff step now runs only in the bulk matrix partition.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"


def _load_workflow() -> dict[str, Any]:
    with _WORKFLOW.open(encoding="utf-8") as handle:
        return cast(dict[str, Any], yaml.safe_load(handle))


def _steps_from_workflow(workflow: Any) -> list[dict[str, Any]]:
    if not isinstance(workflow, dict):
        return []

    jobs = workflow.get("jobs") or {}
    if not isinstance(jobs, dict):
        return []

    test_job = jobs.get("test") or {}
    if not isinstance(test_job, dict):
        return []

    steps = test_job.get("steps") or []
    if not isinstance(steps, list):
        return []

    return [step for step in steps if isinstance(step, dict)]


def _test_job_steps() -> list[dict[str, Any]]:
    return _steps_from_workflow(_load_workflow())


def _find_ruff_step() -> dict[str, Any] | None:
    for step in _test_job_steps():
        run = step.get("run")
        if isinstance(run, str) and "scripts/ci/ruff_ratchet.py" in run:
            return step
    return None


class TestWorkflowStepExtraction:
    """Edge: malformed workflow shapes produce no steps instead of errors."""

    def test_missing_or_null_workflow_sections_return_empty_steps(self) -> None:
        assert _steps_from_workflow(None) == []
        assert _steps_from_workflow({"jobs": None}) == []
        assert _steps_from_workflow({"jobs": {"test": None}}) == []
        assert _steps_from_workflow({"jobs": {"test": {"steps": None}}}) == []

    def test_non_mapping_steps_are_ignored(self) -> None:
        workflow = {
            "jobs": {
                "test": {
                    "steps": [
                        "not-a-step",
                        {"name": "Run ruff", "run": "python scripts/ci/ruff_ratchet.py"},
                    ]
                }
            }
        }
        assert _steps_from_workflow(workflow) == [
            {"name": "Run ruff", "run": "python scripts/ci/ruff_ratchet.py"}
        ]


class TestRuffStepPresence:
    """Positive: the ruff ratchet exists and runs the canonical invocation."""

    def test_workflow_file_exists(self) -> None:
        assert _WORKFLOW.is_file()

    def test_ruff_step_present_in_test_job(self) -> None:
        assert _find_ruff_step() is not None

    def test_ruff_step_runs_canonical_invocation(self) -> None:
        step = _find_ruff_step()
        assert step is not None
        assert step["run"].strip() == "python scripts/ci/ruff_ratchet.py"


class TestRuffStepIsBlockingRatchet:
    """Negative: the ratchet must block changed-file violations."""

    def test_ruff_step_is_not_continue_on_error(self) -> None:
        step = _find_ruff_step()
        assert step is not None
        assert "continue-on-error" not in step

    def test_no_test_step_runs_repo_wide_report_only_ruff(self) -> None:
        repo_wide_report_steps = [
            step
            for step in _test_job_steps()
            if isinstance(step.get("run"), str)
            and "ruff check ." in step["run"]
            and step.get("continue-on-error") is True
        ]
        assert repo_wide_report_steps == []


class TestRuffStepGating:
    """Edge: the step runs once, in the bulk partition."""

    def test_ruff_step_runs_only_in_bulk_partition(self) -> None:
        step = _find_ruff_step()
        assert step is not None
        assert step.get("if") == "matrix.partition == 'bulk'"

    def test_ruff_step_has_no_untrusted_interpolation(self) -> None:
        """The run command must not interpolate untrusted GitHub event data."""
        step = _find_ruff_step()
        assert step is not None
        assert "${{" not in step["run"]

    def test_ruff_step_gets_base_ref_from_environment(self) -> None:
        step = _find_ruff_step()
        assert step is not None
        env = step.get("env")
        assert isinstance(env, dict)
        assert "github.event.pull_request.base.sha" in env["RUFF_RATCHET_BASE_REF"]
