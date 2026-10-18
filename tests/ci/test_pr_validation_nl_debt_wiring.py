"""Wiring test: pr-validation.yml passes the base ref to the NL structural debt ratchet.

Issue #6506. The ratchet's baseline lives in the PR head, so without --base-ref a PR
raises its own allowance in the commit that adds the debt. The test parses the workflow
rather than searching its text (testing.md rule 9).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pr-validation.yml"
_SCRIPT = "scripts/validation/check_nl_structural_debt.py"


def _step() -> dict[str, Any]:
    wf = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = wf["jobs"]["validate-pr"]["steps"]
    matches = [step for step in steps if _SCRIPT in step.get("run", "")]
    assert len(matches) == 1, "Expected exactly one NL structural debt step"
    return matches[0]


def test_ratchet_runs_against_the_fetched_base_ref() -> None:
    lines = [line.strip() for line in _step()["run"].strip().splitlines()]
    commands = [line for line in lines if not line.startswith("#")]
    assert commands == [
        'git fetch origin "$BASE_REF"',
        "uv run --frozen python3 scripts/validation/check_nl_structural_debt.py "
        "--base-ref FETCH_HEAD",
    ]


def test_base_branch_comes_from_the_event_with_a_default() -> None:
    expression = _step()["env"]["BASE_REF"]
    assert expression == "${{ github.base_ref || github.event.repository.default_branch }}"


def test_ratchet_is_unconditional() -> None:
    step = _step()
    assert "if" not in step
    assert "continue-on-error" not in step
