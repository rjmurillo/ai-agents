"""Contract tests for pull request workflow recovery after close and reopen."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"
_CLOSE_ONLY_WORKFLOWS = {
    "milestone-tracking.yml": frozenset({"closed"}),
    "post-pr-retrospective.yml": frozenset({"closed"}),
}


def _pull_request_types(workflow: Path) -> frozenset[str] | None:
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{workflow.name}: expected a mapping"

    # PyYAML parses the bare "on:" key as the boolean True.
    on_block = document.get("on") or document.get(True)
    if not isinstance(on_block, dict):
        return None

    pull_request = on_block.get("pull_request")
    if not isinstance(pull_request, dict):
        return None

    event_types = pull_request.get("types")
    if event_types is None:
        return None

    assert isinstance(event_types, list), (
        f"{workflow.name}: pull_request.types must be a list, "
        f"got {type(event_types).__name__}"
    )
    return frozenset(event_types)


def _workflows_missing_reopened(workflows: Iterable[Path]) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for workflow in workflows:
        event_types = _pull_request_types(workflow)
        if event_types is None or "reopened" in event_types:
            continue
        if _CLOSE_ONLY_WORKFLOWS.get(workflow.name) == event_types:
            continue
        missing[workflow.name] = sorted(event_types)
    return missing


def _all_workflows() -> list[Path]:
    return sorted([*_WORKFLOWS.glob("*.yml"), *_WORKFLOWS.glob("*.yaml")])


def test_active_pull_request_workflows_include_reopened() -> None:
    missing = _workflows_missing_reopened(_all_workflows())

    assert not missing, (
        "Active pull_request workflows with explicit event types must include "
        f"'reopened'. Missing: {missing}"
    )


def test_contract_detects_missing_reopened(tmp_path: Path) -> None:
    workflow = tmp_path / "active.yml"
    workflow.write_text(
        "on:\n  pull_request:\n    types: [opened, synchronize]\n",
        encoding="utf-8",
    )

    assert _workflows_missing_reopened([workflow]) == {
        "active.yml": ["opened", "synchronize"]
    }


def test_contract_accepts_default_pull_request_events(tmp_path: Path) -> None:
    workflow = tmp_path / "default.yml"
    workflow.write_text("on:\n  pull_request:\n", encoding="utf-8")

    assert _workflows_missing_reopened([workflow]) == {}


@pytest.mark.parametrize(
    ("workflow_name", "expected_types"),
    sorted(_CLOSE_ONLY_WORKFLOWS.items()),
)
def test_close_only_workflows_remain_close_only(
    workflow_name: str,
    expected_types: frozenset[str],
) -> None:
    assert _pull_request_types(_WORKFLOWS / workflow_name) == expected_types
