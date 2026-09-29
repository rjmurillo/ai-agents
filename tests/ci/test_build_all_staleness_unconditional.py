"""The whole-tree build_all staleness check must not sit behind a paths filter.

``build_all.py --check`` compares every generator output against its source, so
its input is the tree, not the diff. ``.claude/rules/ci-scripts.md`` ("Path
filters gate the diff, never the tree") requires such a check to run
unconditionally. Issue #5296.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/validate-generated-agents.yml"
CHECK_COMMAND = "build/scripts/build_all.py --check"
FILTER_JOB = "check-paths"


def _jobs() -> dict[str, dict[str, Any]]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return document["jobs"]


def _jobs_running_check() -> dict[str, dict[str, Any]]:
    return {
        name: job
        for name, job in _jobs().items()
        if any(CHECK_COMMAND in str(step.get("run", "")) for step in job.get("steps", []))
    }


def _needs(job: dict[str, Any]) -> list[str]:
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else list(needs)


def test_exactly_one_job_runs_the_staleness_check() -> None:
    assert len(_jobs_running_check()) == 1


def test_staleness_job_does_not_depend_on_the_paths_filter_job() -> None:
    (job,) = _jobs_running_check().values()
    assert FILTER_JOB not in _needs(job)


def test_staleness_job_has_no_job_level_condition() -> None:
    (job,) = _jobs_running_check().values()
    assert "if" not in job


def test_staleness_step_has_no_condition_tied_to_the_filter() -> None:
    (job,) = _jobs_running_check().values()
    for step in job["steps"]:
        assert "if" not in step, f"step {step.get('name')!r} carries an if: condition"


def test_staleness_job_does_not_reference_filter_outputs() -> None:
    (job,) = _jobs_running_check().values()
    rendered = yaml.safe_dump(job)
    assert FILTER_JOB not in rendered
    assert "should-run" not in rendered


def test_filtered_validate_job_no_longer_runs_the_check() -> None:
    assert "validate" not in _jobs_running_check()
