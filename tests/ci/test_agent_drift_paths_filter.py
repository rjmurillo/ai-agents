"""agent-drift-detection.yml must trigger on every path that changes a generated agent file.

``build/generate_agents.py --validate`` compares the whole generated tree with
the templates, so the ``dorny/paths-filter`` entry that decides whether the
``validate`` job runs has to cover every generated-output location. The sibling
workflow ``validate-generated-agents.yml`` runs the same command behind a wider
filter. Before issue #5636 the drift workflow omitted six of those paths, so a
change to only one of them ran the sibling and skipped this check while its
status stayed green.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIFT = REPO_ROOT / ".github/workflows/agent-drift-detection.yml"
SIBLING = REPO_ROOT / ".github/workflows/validate-generated-agents.yml"
PATHS_FILTER_ACTION = "dorny/paths-filter@"

# Generated-output and generator-input locations the sibling filter lists and
# the drift filter once omitted.
GENERATED_SURFACE = (
    "docs/agent-catalog.md",
    "src/claude/**",
    ".claude/**",
    ".github/agents/**",
    ".github/instructions/**",
    ".github/prompts/**",
    ".github/workflows/**",
)


def _agents_filter(workflow: Path) -> list[str]:
    document: dict[str, Any] = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    steps = document["jobs"]["check-paths"]["steps"]
    filters = [s for s in steps if str(s.get("uses", "")).startswith(PATHS_FILTER_ACTION)]
    assert len(filters) == 1, f"{workflow.name}: expected one paths-filter step"
    return yaml.safe_load(filters[0]["with"]["filters"])["agents"]


@pytest.mark.parametrize("pattern", GENERATED_SURFACE)
def test_drift_filter_covers_generated_surface(pattern: str) -> None:
    assert pattern in _agents_filter(DRIFT), (
        f"{DRIFT.name} paths filter omits {pattern!r}: a change to only that path "
        "skips the drift check and reports success"
    )


@pytest.mark.parametrize("pattern", GENERATED_SURFACE)
def test_sibling_filter_still_lists_the_surface(pattern: str) -> None:
    """Guards the guard: if the sibling drops a path, this list is stale."""
    assert pattern in _agents_filter(SIBLING)


def test_drift_filter_keeps_its_own_generator_inputs() -> None:
    """Negative control: widening must not drop the entries it already had."""
    patterns = _agents_filter(DRIFT)
    kept = (
        "templates/**",
        "build/generate_agents.py",
        ".github/workflows/agent-drift-detection.yml",
    )
    assert [p for p in kept if p not in patterns] == []


def test_drift_workflow_has_no_top_level_paths_filter() -> None:
    """A trigger-level ``paths:`` would skip the workflow and its status check."""
    document = yaml.safe_load(DRIFT.read_text(encoding="utf-8"))
    triggers = document.get("on", document.get(True))
    assert "paths" not in triggers["pull_request"]
