"""Tests that lefthook gate jobs include enforcement flags (issue #4313)."""
from __future__ import annotations

from pathlib import Path

import yaml

LEFTHOOK_PATH = Path(__file__).parent.parent / "lefthook.yml"


def _iter_all_jobs(data) -> list[dict]:
    """Recursively yield all named job dicts from any lefthook structure."""
    results = []
    if isinstance(data, dict):
        if "name" in data and "run" in data:
            results.append(data)
        for key in ("jobs", "commands"):
            child = data.get(key)
            if child is not None:
                results.extend(_iter_all_jobs(child))
        for key, val in data.items():
            if key not in ("name", "run", "jobs", "commands", "glob", "skip",
                           "timeout", "parallel", "piped"):
                results.extend(_iter_all_jobs(val))
    elif isinstance(data, list):
        for item in data:
            results.extend(_iter_all_jobs(item))
    return results


class TestMemoryTierGateEnforcement:
    """Memory gate lefthook jobs must include --ci to exit non-zero on violations."""

    def _find_job(self, name: str) -> dict:
        data = yaml.safe_load(LEFTHOOK_PATH.read_text(encoding="utf-8"))
        for job in _iter_all_jobs(data):
            if job.get("name") == name:
                return job
        raise AssertionError(f"Job {name!r} not found in lefthook.yml")

    def test_memory_tier_job_has_ci_flag(self) -> None:
        job = self._find_job("memory-tier")
        run = job.get("run", "")
        assert "--ci" in run, f"memory-tier is missing --ci: {run!r}"

    def test_memory_index_job_has_ci_flag(self) -> None:
        job = self._find_job("memory-index")
        run = job.get("run", "")
        assert "--ci" in run, f"memory-index is missing --ci: {run!r}"
