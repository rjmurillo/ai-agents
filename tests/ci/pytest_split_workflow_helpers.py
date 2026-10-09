"""Readers for the pytest-split cache wiring in pytest.yml.

Imported by test_pytest_split_durations_*.py. The name does not match
`test_*.py`, so pytest never walks it.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"
KEY_PREFIX = "pytest-split-durations-"


@cache
def workflow_jobs() -> dict[str, Any]:
    """The `jobs` mapping of pytest.yml. Callers must not mutate it."""
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def steps_using(job: str, action: str) -> list[dict[str, Any]]:
    """Steps of ``job`` that run ``action`` (for example ``actions/cache/save``)."""
    return [
        s for s in workflow_jobs()[job]["steps"] if str(s.get("uses", "")).startswith(action + "@")
    ]


def durations_saves() -> list[tuple[str, dict[str, Any]]]:
    """Every (job, step) that saves a cache under the durations key prefix."""
    return [
        (job, step)
        for job in workflow_jobs()
        for step in steps_using(job, "actions/cache/save")
        if step["with"]["key"].startswith(KEY_PREFIX)
    ]


def merge_step() -> dict[str, Any]:
    (step,) = [
        s for s in workflow_jobs()["test-durations"]["steps"] if s.get("id") == "merge-durations"
    ]
    return step
