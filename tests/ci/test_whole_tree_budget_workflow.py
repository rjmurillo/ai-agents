"""No job in the instruction budget workflow may pass without measuring.

Issue #4345. The budget is a sum over the whole always-on corpus, so a path
filter over the diff cannot decide it. When the filter missed, ``Validate
budget`` was skipped and a companion ``Skip budget (no changes)`` job reported
success in its place. That is a fresh green tick asserting only that the diff
was uninteresting, and it is how ``main`` sat 201 bytes over ceiling with a
green Instruction Budget run at ``a72ee868c``.

No required status check depends on this workflow (ruleset 11104075 names 17
contexts, none of them a job here), so the skip-announcer satisfied nothing.
The invariant this pins: every job in this workflow runs the validator, and no
job is gated on a condition.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "instruction-budget.yml"

VALIDATOR_MODULE = "scripts.validation.instruction_budget"


def _load(path: Path) -> dict[Any, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path.name} is not a workflow mapping"
    return loaded


def _job_runs_validator(job: dict[Any, Any]) -> bool:
    steps = job.get("steps")
    if not isinstance(steps, list):
        return False
    for step in steps:
        run = step.get("run") if isinstance(step, dict) else None
        if isinstance(run, str) and VALIDATOR_MODULE in run:
            return True
    return False


def _unmeasured_success_errors(workflow: dict[Any, Any]) -> list[str]:
    """Report jobs that can report success without measuring the corpus."""
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return ["workflow declares no jobs"]

    errors: list[str] = []
    for name, job in jobs.items():
        if not isinstance(job, dict):
            errors.append(f"{name}: job is not a mapping")
            continue
        if "if" in job:
            errors.append(
                f"{name}: gated on a condition. A whole-tree sum cannot be "
                "decided from the diff, and a skipped measurement reports "
                "success in its place."
            )
        if not _job_runs_validator(job):
            errors.append(
                f"{name}: never runs {VALIDATOR_MODULE}, so a green result "
                "from it asserts nothing about the tree."
            )
    return errors


def test_every_job_measures_the_corpus() -> None:
    assert _unmeasured_success_errors(_load(WORKFLOW)) == []


def test_pull_requests_and_main_pushes_both_reach_the_validator() -> None:
    workflow = _load(WORKFLOW)
    triggers = workflow.get(True, workflow.get("on"))

    assert isinstance(triggers, dict)
    assert "pull_request" in triggers
    assert triggers["push"]["branches"] == ["main"]
    assert _unmeasured_success_errors(workflow) == []


def test_detector_flags_a_skip_announcer_job() -> None:
    workflow = {
        "jobs": {
            "validate-budget": {
                "steps": [{"run": f"python -m {VALIDATOR_MODULE} --ci"}],
            },
            "skip-budget": {
                "if": "needs.check-paths.outputs.should-run-budget != 'true'",
                "steps": [{"run": "echo 'no changes detected'"}],
            },
        }
    }

    errors = _unmeasured_success_errors(workflow)

    assert any("skip-budget" in error for error in errors)
    assert not any("validate-budget" in error for error in errors)


def test_detector_flags_a_gated_validator_job() -> None:
    workflow = {
        "jobs": {
            "validate-budget": {
                "if": "needs.check-paths.outputs.should-run-budget == 'true'",
                "steps": [{"run": f"python -m {VALIDATOR_MODULE} --ci"}],
            }
        }
    }

    errors = _unmeasured_success_errors(workflow)

    assert len(errors) == 1
    assert errors[0].startswith("validate-budget: gated on a condition")


def test_detector_accepts_an_ungated_measuring_job() -> None:
    workflow = {
        "jobs": {
            "validate-budget": {"steps": [{"run": f"uv run python -m {VALIDATOR_MODULE} --ci"}]}
        }
    }

    assert _unmeasured_success_errors(workflow) == []
