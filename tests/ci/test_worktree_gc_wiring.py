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
    assert job["timeout"] == "2m"


def test_worktree_gc_report_is_in_pre_push_group() -> None:
    data = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    pre_push = data["pre-push"]["jobs"]
    group_jobs = [job for group in pre_push if "group" in group for job in group["group"]["jobs"]]
    assert any(job.get("name") == "worktree-gc-report" for job in group_jobs)
