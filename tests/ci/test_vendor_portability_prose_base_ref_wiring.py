"""Wiring test: the prose portability ratchet reads its ceiling from the base branch.

Issue #6506. Without ``--base-ref`` the baseline in the PR head is the only ceiling, so a
PR could raise it in the commit that adds the references. A push to main compares with the
tip before the push, since ``origin/main`` already holds the pushed commit. The test parses
the YAML rather than searching its text (testing.md rule 9).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "validate-vendor-portability.yml"
)
_STEP_NAME = "Check skill prose portability ratchet"


def _steps() -> list[dict[str, Any]]:
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps: list[dict[str, Any]] = workflow["jobs"]["validate-portability"]["steps"]
    return steps


def _prose_step() -> dict[str, Any]:
    matches = [step for step in _steps() if step.get("name") == _STEP_NAME]
    assert len(matches) == 1, "Expected exactly one prose ratchet step"
    return matches[0]


def test_ratchet_passes_the_base_branch_as_its_ceiling_ref() -> None:
    assert _prose_step()["run"].strip() == (
        "uv run --frozen python scripts/validation/check_skill_md_portability.py "
        '--base-ref "$BASE_REF"'
    )


def test_ratchet_stays_unconditional_and_failing() -> None:
    step = _prose_step()
    assert "if" not in step
    assert "continue-on-error" not in step


def test_base_ref_follows_the_event_kind() -> None:
    """A PR uses origin/<base>. A push uses the tip before it, since origin/main already holds
    the pushed commit. A dispatch has neither, so origin/main backs it."""
    expression = _prose_step()["env"]["BASE_REF"]
    assert expression == (
        "${{ github.base_ref && format('origin/{0}', github.base_ref) "
        "|| github.event.before || 'origin/main' }}"
    )


def test_checkout_is_full_depth_so_the_base_ref_and_fork_point_exist() -> None:
    checkout = next(s for s in _steps() if s.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0
