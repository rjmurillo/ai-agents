"""The ADR uniqueness check must not sit behind a paths filter.

``check_adr_uniqueness.py`` globs every ``ADR-*.md`` in the architecture
directory, so its input is the tree, not the diff.
``.claude/rules/ci-scripts.md`` ("Path filters gate the diff, never the
tree") requires such a check to run unconditionally. Issue #5114: two ADR-094
documents coexisted because the gate could skip while reporting success.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "validate-adr-number-uniqueness.yml"

VALIDATOR = "scripts/validation/check_adr_uniqueness.py"
PATHS_FILTER_ACTION = "dorny/paths-filter"


def _load(path: Path) -> dict[Any, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path.name} is not a workflow mapping"
    return loaded


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML reads the bare key `on` as boolean True.
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict), "workflow declares no trigger mapping"
    return triggers


def _runs_validator(job: dict[Any, Any]) -> bool:
    steps = job.get("steps")
    if not isinstance(steps, list):
        return False
    return any(isinstance(step, dict) and VALIDATOR in str(step.get("run", "")) for step in steps)


def gating_errors(workflow: dict[Any, Any]) -> list[str]:
    """Report any way this workflow can pass without measuring the tree."""
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        return ["workflow declares no jobs"]

    errors: list[str] = []
    for name, job in jobs.items():
        if "if" in job:
            errors.append(f"{name}: job gated on a condition")
        if "needs" in job:
            errors.append(f"{name}: job waits on another job that can gate it")
        if PATHS_FILTER_ACTION in yaml.safe_dump(job):
            errors.append(f"{name}: uses {PATHS_FILTER_ACTION}")
        if not _runs_validator(job):
            errors.append(f"{name}: never runs {VALIDATOR}")
        for step in job.get("steps", []):
            if isinstance(step, dict) and "if" in step and "failure()" not in str(step["if"]):
                errors.append(f"{name}: step {step.get('name')!r} carries an if: condition")
    return errors


def test_live_workflow_has_no_gating() -> None:
    assert gating_errors(_load(WORKFLOW)) == []


def test_live_workflow_runs_the_validator_in_exactly_one_job() -> None:
    jobs = _load(WORKFLOW)["jobs"]
    assert [name for name, job in jobs.items() if _runs_validator(job)] == ["validate-adr-numbers"]


def test_live_workflow_keeps_no_skip_announcer() -> None:
    """Negative: a job that reports success without measuring must not return."""
    rendered = WORKFLOW.read_text(encoding="utf-8").lower()
    assert "skip-validation" not in rendered
    assert "should-run-adrs" not in rendered


def test_live_workflow_triggers_on_every_pr_and_main_push() -> None:
    triggers = _triggers(_load(WORKFLOW))
    assert triggers["push"] == {"branches": ["main"]}
    assert triggers["pull_request"]["branches"] == ["main"]
    assert "paths" not in triggers["pull_request"]
    assert "paths-ignore" not in triggers["pull_request"]
    assert "paths" not in triggers["push"]
    assert "workflow_dispatch" in triggers


def test_live_workflow_keeps_the_job_name_unchanged() -> None:
    """Edge: the check name that branch rulesets may name stays stable."""
    job = _load(WORKFLOW)["jobs"]["validate-adr-numbers"]
    assert job["name"] == "Validate ADR Number Uniqueness"


_GATED = """
name: x
on: {push: {branches: [main]}}
jobs:
  check-changes:
    runs-on: ubuntu-latest
    steps:
      - uses: dorny/paths-filter@abc
  validate-adr-numbers:
    needs: check-changes
    if: needs.check-changes.outputs.should-run-adrs == 'true'
    runs-on: ubuntu-latest
    steps:
      - run: python3 scripts/validation/check_adr_uniqueness.py
"""


def test_detector_flags_the_pre_fix_shape() -> None:
    """Negative control: the detector catches the filtered, skippable layout."""
    errors = gating_errors(yaml.safe_load(_GATED))
    assert any("uses dorny/paths-filter" in e for e in errors)
    assert any("gated on a condition" in e for e in errors)
    assert any("waits on another job" in e for e in errors)
    assert any("check-changes: never runs" in e for e in errors)


def test_detector_flags_a_gated_step() -> None:
    """Edge: an if: on a step is a gate; only failure() remediation is exempt."""
    workflow = yaml.safe_load(
        """
jobs:
  v:
    runs-on: ubuntu-latest
    steps:
      - run: python3 scripts/validation/check_adr_uniqueness.py
      - name: gated
        if: github.event_name == 'push'
        run: echo hi
      - name: remediation
        if: failure()
        run: echo fix
"""
    )
    errors = gating_errors(workflow)
    assert errors == ["v: step 'gated' carries an if: condition"]


def test_detector_rejects_an_empty_workflow() -> None:
    assert gating_errors({"jobs": {}}) == ["workflow declares no jobs"]
    assert gating_errors({}) == ["workflow declares no jobs"]
