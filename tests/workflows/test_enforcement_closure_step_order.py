"""The dispatch-closure step stays last in its job (issue #6506).

The head fetch is depth-limited, so after it the base checkout may be shallow at the
head's ancestor. A later step that walks history would fail or answer wrongly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "enforcement-closure.yml"
SCRIPT = "verify_dispatch_closure.py"


def _steps() -> list[dict[str, Any]]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["dispatch-closure"]["steps"]


def _runs_script(step: dict[str, Any]) -> bool:
    return SCRIPT in str(step.get("run", ""))


def _closure_step_is_last(steps: list[dict[str, Any]]) -> bool:
    runs = [i for i, step in enumerate(steps) if _runs_script(step)]
    return len(runs) == 1 and runs[0] == len(steps) - 1


def test_the_closure_step_is_the_last_step_of_its_job() -> None:
    assert _closure_step_is_last(_steps())


def test_a_step_added_after_the_closure_step_is_detected() -> None:
    """Negative control: the check fails when a step follows the closure step."""
    steps = [*_steps(), {"name": "Walk history", "run": "git log --oneline"}]

    assert not _closure_step_is_last(steps)


def test_a_job_without_the_closure_step_is_detected() -> None:
    """Edge: a renamed script cannot pass by matching nothing."""
    assert not _closure_step_is_last([{"name": "Other", "run": "echo hi"}])


def test_the_job_checks_out_the_base_with_full_history_first() -> None:
    first_checkout = next(
        s for s in _steps() if str(s.get("uses", "")).startswith("actions/checkout@")
    )

    assert first_checkout["with"]["fetch-depth"] == 0
    assert first_checkout["with"]["persist-credentials"] is False
