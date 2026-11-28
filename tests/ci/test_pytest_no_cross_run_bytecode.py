"""pytest.yml must not restore Python bytecode that an earlier run produced.

Owner decision D2 (2026-11-28) for the pytest bytecode cache lane: no job
executes bytecode it did not produce in the same run. A restored pyc carries a
source hash that proves freshness, not authorship, so a cache writer can pair
a payload with a correct header. These tests fail on any step that moves
bytecode between runs through an Actions cache or an artifact.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.ci.pytest_split_workflow_helpers import WORKFLOW, workflow_jobs

_CROSS_RUN_ACTIONS = (
    "actions/cache@",
    "actions/cache/restore@",
    "actions/cache/save@",
    "actions/download-artifact@",
    "actions/upload-artifact@",
)
_BYTECODE_MARKERS = ("bytecode", "pycache", ".pyc")


def _all_steps() -> list[tuple[str, dict[str, Any]]]:
    return [(job, step) for job, body in workflow_jobs().items() for step in body.get("steps", [])]


def _mentions_bytecode(step: dict[str, Any]) -> bool:
    text = json.dumps(step.get("with", {})).lower()
    return any(marker in text for marker in _BYTECODE_MARKERS)


def test_no_cache_or_artifact_step_carries_bytecode() -> None:
    offenders = [
        f"{job}: {step.get('name', step.get('uses'))}"
        for job, step in _all_steps()
        if str(step.get("uses", "")).startswith(_CROSS_RUN_ACTIONS) and _mentions_bytecode(step)
    ]
    assert offenders == [], f"cross-run bytecode movement: {offenders}"


def test_no_job_sets_a_bytecode_prefix_that_a_restore_could_fill() -> None:
    offenders = [
        job
        for job, body in workflow_jobs().items()
        if "PYTHONPYCACHEPREFIX" in json.dumps(body.get("env", {}))
        or any("PYTHONPYCACHEPREFIX" in json.dumps(s.get("env", {})) for s in body.get("steps", []))
    ]
    assert offenders == [], f"jobs setting PYTHONPYCACHEPREFIX: {offenders}"


@pytest.mark.parametrize("marker", ["pytest-bytecode", "publish-bytecode-cache"])
def test_the_workflow_text_names_no_bytecode_cache_key_or_job(marker: str) -> None:
    assert marker not in WORKFLOW.read_text(encoding="utf-8")


def test_the_guard_detects_a_bytecode_cache_step() -> None:
    """Negative control: the matcher flags the step shape this module forbids."""
    step = {
        "uses": "actions/cache/restore@0000000000000000000000000000000000000000",
        "with": {"path": "${{ runner.temp }}/pytest-bytecode-cache", "key": "k"},
    }
    assert str(step["uses"]).startswith(_CROSS_RUN_ACTIONS)
    assert _mentions_bytecode(step)
