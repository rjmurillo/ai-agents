"""Structural tests for worktree GC automation wiring (issue #4193)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"


def _iter_jobs(node: Any):
    if isinstance(node, dict):
        if "name" in node and "run" in node:
            yield node
        for value in node.values():
            yield from _iter_jobs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_jobs(item)


def _lefthook_job(name: str) -> dict[str, Any]:
    data = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    matches = [job for job in _iter_jobs(data) if job.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def test_worktree_gc_report_runs_in_pre_push_without_apply() -> None:
    job = _lefthook_job("worktree-gc-report")
    assert job["run"] == "uv run --frozen python scripts/maintenance/gc_worktrees.py"
    assert "--apply" not in job["run"]
    assert job["timeout"] == "5m"


def test_worktree_gc_report_is_in_pre_push_group() -> None:
    data = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    pre_push = data["pre-push"]["jobs"]
    group_jobs = [job for group in pre_push if "group" in group for job in group["group"]["jobs"]]
    assert any(job.get("name") == "worktree-gc-report" for job in group_jobs)


def _duration_seconds(value: str) -> float:
    """Convert a lefthook duration such as '5m' or '90s' to seconds."""
    units = {"h": 3600.0, "m": 60.0, "s": 1.0}
    if value[-1] in units:
        return float(value[:-1]) * units[value[-1]]
    return float(value)


def test_the_worst_case_report_fits_inside_its_lefthook_timeout() -> None:
    """The budget and the job cap must not drift into a push-rejecting pair.

    The report mutates nothing and always exits 0 on a completed run, so the
    only way it can reject a push is by exceeding this cap. Worst case is the
    two setup git calls made before the deadline is even established, plus the
    budget itself, plus one final inspection that started just under the
    deadline and makes up to three git calls.
    """
    from scripts.maintenance.gc_worktrees import (
        _DEFAULT_TIME_BUDGET_SECONDS,
        _GIT_TIMEOUT_SECONDS,
    )

    setup_git_calls = 2
    git_calls_per_inspection = 3
    worst_case = (
        setup_git_calls * _GIT_TIMEOUT_SECONDS
        + _DEFAULT_TIME_BUDGET_SECONDS
        + git_calls_per_inspection * _GIT_TIMEOUT_SECONDS
    )
    cap = _duration_seconds(str(_lefthook_job("worktree-gc-report")["timeout"]))
    assert worst_case < cap, f"worst case {worst_case}s does not fit inside the {cap}s job timeout"
