"""Contract tests for the report-only ruff step in pytest.yml (Issue #2194).

The repository carries a pre-existing backlog of ruff findings (2026 as of
2026-06-01), so the CI ruff step is deliberately report-only
(`continue-on-error: true`) and must not block merges. These tests pin that
contract so a later edit cannot silently turn the step into a blocking gate, or
drop the gating/skip condition, without a test failing first.

When the backlog reaches zero and the step is promoted to a blocking gate, the
report-only assertions here are expected to change in the same PR that drops
`continue-on-error`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"


def _load_workflow() -> dict[str, Any]:
    with _WORKFLOW.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


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
        if isinstance(run, str) and "ruff check" in run:
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
                        {"name": "Run ruff", "run": "ruff check . --output-format=github"},
                    ]
                }
            }
        }
        assert _steps_from_workflow(workflow) == [
            {"name": "Run ruff", "run": "ruff check . --output-format=github"}
        ]


class TestRuffStepPresence:
    """Positive: the ruff step exists and runs the canonical invocation."""

    def test_workflow_file_exists(self) -> None:
        assert _WORKFLOW.is_file()

    def test_ruff_step_present_in_test_job(self) -> None:
        assert _find_ruff_step() is not None

    def test_ruff_step_runs_canonical_invocation(self) -> None:
        step = _find_ruff_step()
        assert step is not None
        # Matches the baseline command `ruff check .`; CI adds GitHub
        # annotations via --output-format=github.
        assert step["run"].strip() == "ruff check . --output-format=github"


class TestRuffStepIsReportOnly:
    """Negative: the step must not block merges while the backlog is non-zero."""

    def test_ruff_step_is_continue_on_error(self) -> None:
        step = _find_ruff_step()
        assert step is not None
        assert step.get("continue-on-error") is True

    def test_no_other_test_step_runs_ruff_as_a_gate(self) -> None:
        """No additional ruff invocation in the test job lacks continue-on-error."""
        gating = [
            step
            for step in _test_job_steps()
            if isinstance(step.get("run"), str)
            and "ruff check" in step["run"]
            and step.get("continue-on-error") is not True
        ]
        assert gating == []


class TestRuffStepGating:
    """Edge: the step honors the existing skip gate and carries no injection surface."""

    def test_ruff_step_gated_by_skip_condition(self) -> None:
        step = _find_ruff_step()
        assert step is not None
        # Reuses the same gate every other step in the test job uses so the
        # ruff step is skipped when no Python files changed.
        assert step.get("if") == "steps.should-run.outputs.skip != 'true'"

    def test_ruff_step_has_no_untrusted_interpolation(self) -> None:
        """The run command must not interpolate untrusted GitHub event data."""
        step = _find_ruff_step()
        assert step is not None
        assert "${{" not in step["run"]
