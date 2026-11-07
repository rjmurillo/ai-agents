"""Secret-bearing pr-maintenance steps run only code from the trusted checkout.

The ``process-prs`` job switches the workspace to a PR head (the conflict
scripts run ``git checkout <head_ref>``). Any later step that holds
the write-scoped ``github.token`` or ``ANTHROPIC_API_KEY`` and runs workspace
code would execute PR-controlled code with those credentials. The job therefore checks out a trusted
copy at ``.trusted-helper`` and every such step must run from it.

The action side is pinned in ``test_ai_review_action_root.py``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-maintenance.yml"
TRUSTED = ".trusted-helper/"
TRUSTED_STEP_NAME = "Checkout trusted push helper"
CREDENTIAL_MARKERS = ("secrets.", "github.token")
PATH_INPUTS = ("prompt-file", "execute-script")
SCRIPT_CALL = re.compile(r"\b(?:python3?|uv run\b[^\n]*?\bpython)\s+\"?([^\s\"]+)")


def _bears_credential(step: dict[str, Any]) -> bool:
    dumped = yaml.safe_dump(step)
    return any(marker in dumped for marker in CREDENTIAL_MARKERS)


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps_after_trusted_checkout(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    steps = workflow["jobs"]["process-prs"]["steps"]
    names = [step.get("name") for step in steps]
    return steps[names.index(TRUSTED_STEP_NAME) + 1 :]


def untrusted_secret_steps(steps: list[dict[str, Any]]) -> list[str]:
    """Return a reason for each secret-bearing step that runs non-trusted code."""
    problems: list[str] = []
    for step in steps:
        if not _bears_credential(step):
            continue
        name = step.get("name", "<unnamed>")
        uses = step.get("uses")
        if uses is not None and not uses.startswith(f"./{TRUSTED}"):
            problems.append(f"{name}: uses {uses}")
        for key in PATH_INPUTS:
            value = (step.get("with") or {}).get(key)
            if value and not value.startswith(TRUSTED):
                problems.append(f"{name}: {key} {value}")
        for target in SCRIPT_CALL.findall(step.get("run", "")):
            if not target.startswith(TRUSTED):
                problems.append(f"{name}: runs {target}")
    return problems


def test_secret_bearing_steps_after_trusted_checkout_run_trusted_code() -> None:
    steps = _steps_after_trusted_checkout(_load(WORKFLOW))
    assert untrusted_secret_steps(steps) == []


def test_the_invariant_covers_every_secret_bearing_step() -> None:
    steps = _steps_after_trusted_checkout(_load(WORKFLOW))
    secret_steps = [s for s in steps if _bears_credential(s)]
    actions = [s for s in secret_steps if s.get("uses")]
    scripts = [s for s in secret_steps if SCRIPT_CALL.search(s.get("run", ""))]
    assert len(actions) == 2
    assert len(scripts) == 4
    assert len(secret_steps) == len(actions) + len(scripts)


def test_trusted_checkout_is_full_and_pinned_to_the_workflow_sha() -> None:
    steps = _load(WORKFLOW)["jobs"]["process-prs"]["steps"]
    step = next(s for s in steps if s.get("name") == TRUSTED_STEP_NAME)
    assert step["with"]["path"] == ".trusted-helper"
    assert step["with"]["ref"] == "${{ github.sha }}"
    assert "sparse-checkout" not in step["with"]
    assert step["with"]["persist-credentials"] is False


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        (
            {"name": "a", "uses": "./.github/actions/ai-review", "with": {"k": "${{ secrets.K }}"}},
            1,
        ),
        (
            {
                "name": "b",
                "uses": "./.trusted-helper/.github/actions/ai-review",
                "with": {"prompt-file": ".github/prompts/x.md", "k": "${{ secrets.K }}"},
            },
            1,
        ),
        (
            {
                "name": "c",
                "uses": "./.trusted-helper/.github/actions/ai-review",
                "with": {"execute-script": ".claude/s.py", "k": "${{ secrets.K }}"},
            },
            1,
        ),
        ({"name": "d", "env": {"T": "${{ secrets.K }}"}, "run": "python3 scripts/ci/x.py"}, 1),
        (
            {
                "name": "e",
                "env": {"T": "${{ secrets.K }}"},
                "run": "uv run --frozen python scripts/x.py",
            },
            1,
        ),
        (
            {
                "name": "f",
                "env": {"T": "${{ secrets.K }}"},
                "run": "python3 .trusted-helper/scripts/ci/x.py",
            },
            0,
        ),
        ({"name": "g", "run": "python3 scripts/ci/x.py"}, 0),
    ],
)
def test_checker_flags_untrusted_secret_steps_only(step: dict[str, Any], expected: int) -> None:
    assert len(untrusted_secret_steps([step])) == expected


def test_discover_prs_token_can_read_the_status_rollup() -> None:
    """github.token sees only declared scopes, and discovery reads statusCheckRollup."""
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert workflow["jobs"]["discover-prs"]["permissions"] == {
        "checks": "read",
        "contents": "read",
        "pull-requests": "read",
        "statuses": "read",
    }
