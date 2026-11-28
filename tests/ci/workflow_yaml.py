"""Load the jobs of a GitHub Actions workflow file for CI-ownership tests."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_jobs(path: Path) -> dict[str, dict]:
    """Return the ``jobs`` mapping of the workflow at ``path``."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    jobs = data.get("jobs")
    assert isinstance(jobs, dict)
    return jobs
