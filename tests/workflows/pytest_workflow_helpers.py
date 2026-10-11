"""Loaders for tests about the `testmon-seed` job in pytest.yml (issue #6239).

The name does not match `test_*.py`, so pytest never walks it.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pytest.yml"
JOB_NAME = "testmon-seed"


@functools.lru_cache(maxsize=1)
def workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def seed_job() -> dict[str, Any]:
    return workflow()["jobs"][JOB_NAME]


def seed_step(name: str) -> dict[str, Any]:
    return next(step for step in seed_job()["steps"] if step.get("name") == name)
