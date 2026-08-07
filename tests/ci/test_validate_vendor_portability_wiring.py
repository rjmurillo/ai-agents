"""Structural tests for validate-vendor-portability.yml CI wiring (issues #4198, #4195).

Verifies that the prose portability ratchet (check_skill_md_portability.py) is
wired into the CI workflow so a merge that bypasses the local pre-push hook
cannot silently skip the check and leave main red.

Each test is a negative control: removing the structural property causes a test
failure before anything runs in CI.  Tests parse the YAML rather than
substring-searching raw text to avoid the 300-character window trap that let
commented-out YAML pass substring checks in issue #4041.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "validate-vendor-portability.yml"
)
_STEP_NAME = "Check skill prose portability ratchet"
_SCRIPT = "check_skill_md_portability.py"
_BASELINE = "skill_md_portability_baseline.json"


def _load_workflow() -> Any:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _validate_job_steps() -> Any:
    wf = _load_workflow()
    return wf["jobs"]["validate-portability"]["steps"]


def _filter_patterns() -> Any:
    wf = _load_workflow()
    check_steps = wf["jobs"]["check-changes"]["steps"]
    filter_step = next(
        (s for s in check_steps if s.get("id") == "filter"),
        None,
    )
    assert filter_step is not None, "paths-filter step (id: filter) not found"
    inner = yaml.safe_load(filter_step["with"]["filters"])
    return inner["skills"]


def test_prose_portability_step_present() -> None:
    """The validate-portability job must contain the prose portability step."""
    steps = _validate_job_steps()
    names = [s.get("name") for s in steps]
    assert _STEP_NAME in names, (
        f"Step {_STEP_NAME!r} is missing from the validate-portability job. "
        "Without it, a PR that adds prose upstream-path references escapes CI."
    )


def test_prose_portability_step_calls_correct_script() -> None:
    """The prose portability step must invoke check_skill_md_portability.py."""
    steps = _validate_job_steps()
    step = next((s for s in steps if s.get("name") == _STEP_NAME), None)
    assert step is not None, f"Step {_STEP_NAME!r} not found"
    run_cmd: str = step.get("run", "")
    assert _SCRIPT in run_cmd, (
        f"Step {_STEP_NAME!r} run field {run_cmd!r} does not invoke {_SCRIPT}."
    )


def test_prose_portability_script_in_filter() -> None:
    """The paths-filter must include the prose portability script."""
    patterns = _filter_patterns()
    target = f"scripts/validation/{_SCRIPT}"
    assert any(target in p for p in patterns), (
        f"paths-filter skills block is missing {target!r}. "
        "Without this, a PR that only changes the script skips the CI check."
    )


def test_prose_portability_baseline_in_filter() -> None:
    """The paths-filter must include the prose portability baseline file."""
    patterns = _filter_patterns()
    target = f"scripts/validation/{_BASELINE}"
    assert any(target in p for p in patterns), (
        f"paths-filter skills block is missing {target!r}. "
        "Without this, a widened baseline bypasses the CI gate."
    )


def test_drift_runtime_dependencies_in_filter() -> None:
    """Every module the checker imports at runtime must be in the paths-filter.

    A PR that changes only one of these alters the checker's behavior while
    leaving should-run-vendor false, so the job skips the code that changed.
    """
    patterns = _filter_patterns()
    for target in (
        "scripts/validation/check_skill_md_drift.py",
        "scripts/validation/tracked_paths.py",
    ):
        assert any(target in p for p in patterns), (
            f"paths-filter skills block is missing {target!r}. "
            "Without this, a PR that only changes that module skips the check."
        )
