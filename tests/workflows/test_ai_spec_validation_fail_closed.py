"""ai-spec-validation.yml must hand step outcomes to its fail-closed gate.

The traceability and completeness review steps carry ``continue-on-error`` so
a crash cannot skip the report steps. That construct also hides the crash from
the job. ``check_spec_failures.py`` is the fail-closed adapter, but it can only
fail closed on a signal it receives. These tests pin that the workflow passes
each review step's ``outcome`` (issue #5636).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

_WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ai-spec-validation.yml"
)
_REVIEW_STEP_IDS = ("trace", "completeness")


def _steps() -> list[dict[str, Any]]:
    document = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]["validate-spec"]["steps"]


def _step_by_id(step_id: str) -> dict[str, Any]:
    matches = [step for step in _steps() if step.get("id") == step_id]
    assert len(matches) == 1, f"expected one step with id {step_id!r}, found {len(matches)}"
    return matches[0]


def _gate_step() -> dict[str, Any]:
    matches = [
        step for step in _steps()
        if "check_spec_failures.py" in str(step.get("run", ""))
    ]
    assert len(matches) == 1, "expected exactly one check_spec_failures.py step"
    return matches[0]


@pytest.mark.parametrize("step_id", _REVIEW_STEP_IDS)
def test_review_step_outcome_reaches_the_gate(step_id: str) -> None:
    env = _gate_step()["env"]
    key = f"{'TRACE' if step_id == 'trace' else 'COMPLETENESS'}_OUTCOME"
    assert env.get(key) == f"${{{{ steps.{step_id}.outcome }}}}"


@pytest.mark.parametrize("step_id", _REVIEW_STEP_IDS)
def test_review_step_still_continues_on_error(step_id: str) -> None:
    """The adapter, not the removal of continue-on-error, is the hardening."""
    assert _step_by_id(step_id).get("continue-on-error") is True


def test_gate_step_is_not_itself_swallowed() -> None:
    step = _gate_step()
    assert "continue-on-error" not in step
    assert "|| true" not in str(step.get("run", ""))


def test_gate_runs_whenever_a_review_step_runs() -> None:
    """A review step that runs must always be followed by the gate."""
    gate_if = str(_gate_step()["if"])
    for step_id in _REVIEW_STEP_IDS:
        review_if = str(_step_by_id(step_id)["if"])
        assert review_if == gate_if, f"{step_id} and the gate use different conditions"


def test_gate_is_scoped_to_runs_that_have_specs() -> None:
    """The gate must not run, and must not fail, when no spec was referenced."""
    gate_if = str(_gate_step()["if"])
    assert "steps.should-run.outputs.skip != 'true'" in gate_if
    assert "steps.spec-ref.outputs.has_specs == 'true'" in gate_if
