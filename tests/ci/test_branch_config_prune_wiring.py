"""Structural tests for the branch-config prune report wiring (issue #5360)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_LEFTHOOK = Path(__file__).resolve().parents[2] / "lefthook.yml"
_JOB = "branch-config-prune-report"


def _jobs(node: Any):
    if isinstance(node, dict):
        if "name" in node and "run" in node:
            yield node
        for value in node.values():
            yield from _jobs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _jobs(item)


def _job() -> dict[str, Any]:
    data = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    matches = [job for job in _jobs(data["pre-push"]) if job["name"] == _JOB]
    assert len(matches) == 1
    return matches[0]


def test_runs_the_prune_script_report_only_in_pre_push() -> None:
    run = _job()["run"]
    assert run.endswith(
        "-- uv run --frozen python scripts/maintenance/prune_branch_config.py --fail-on-stale"
    )
    assert "--apply" not in run


def test_stale_sections_map_to_the_reporter_findings_exit() -> None:
    assert "--findings-exit 1" in _job()["run"]


def test_run_string_carries_no_yaml_comment_character() -> None:
    assert "#" not in _job()["run"]
