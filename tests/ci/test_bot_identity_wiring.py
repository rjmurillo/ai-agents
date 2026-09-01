"""The bot identity diagnostic is wired where API-heavy work runs.

Issue #4607: the mis-issued ``BOT_PAT`` stayed invisible because no
unconditional step reported the credential's resolved identity. These tests
parse the YAML (never substring-match, per .claude/rules/testing.md MUST 9)
and fail when a step is removed, renamed, detached from the module, gated
behind a condition, or flipped to strict mode. Unconditional and non-strict
are the two rollout properties: a condition re-hides the identity (which is
what hid #4607), and strict mode before the owner rotates the secret would
turn every consumer red.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION_PATH = REPO_ROOT / ".github" / "actions" / "ai-review" / "action.yml"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
MODULE_INVOCATION = "check_bot_identity.py"
EXPECTED_BOT_ID = "250269933"

WORKFLOW_CONSUMERS = [
    ("pr-maintenance.yml", "discover-prs"),
    ("ai-metrics-analysis.yml", "analyze-metrics"),
    ("update-reviewer-stats.yml", "update-stats"),
    ("auto-assign-reviewer.yml", "assign-reviewer"),
]


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _identity_steps(steps: list[dict]) -> list[dict]:
    return [step for step in steps if MODULE_INVOCATION in (step.get("run") or "")]


def _assert_identity_step(step: dict, expected_token: str) -> None:
    assert step["env"]["IDENTITY_TOKEN"] == expected_token
    assert str(step["env"]["EXPECTED_BOT_ID"]) == EXPECTED_BOT_ID
    assert "if" not in step, (
        "the identity step must be unconditional; gating it behind a "
        "condition is what hid issue #4607"
    )
    assert "IDENTITY_STRICT" not in step.get("env", {}), (
        "strict mode blocks every run while the secret is still mis-issued; "
        "enable it only after the owner rotates BOT_PAT"
    )


class TestAiReviewAction:
    def test_identity_step_is_unconditional_non_strict_and_bound_to_bot_pat(self):
        action = _load(ACTION_PATH)

        steps = _identity_steps(action["runs"]["steps"])
        assert len(steps) == 1, "exactly one identity step in the ai-review action"
        _assert_identity_step(steps[0], "${{ inputs.bot-pat }}")


class TestWorkflowConsumers:
    @pytest.mark.parametrize(("workflow", "job"), WORKFLOW_CONSUMERS)
    def test_job_reports_bot_pat_identity_unconditionally(self, workflow, job):
        parsed = _load(WORKFLOWS / workflow)

        steps = _identity_steps(parsed["jobs"][job]["steps"])
        assert len(steps) == 1, f"exactly one identity step in {workflow}:{job}"
        _assert_identity_step(steps[0], "${{ secrets.BOT_PAT }}")

    @pytest.mark.parametrize(("workflow", "job"), WORKFLOW_CONSUMERS)
    def test_identity_step_runs_before_the_first_bot_pat_api_step(self, workflow, job):
        parsed = _load(WORKFLOWS / workflow)

        steps = parsed["jobs"][job]["steps"]
        first_identity = next(
            i for i, s in enumerate(steps) if MODULE_INVOCATION in (s.get("run") or "")
        )
        bot_pat_consumers = [
            i
            for i, s in enumerate(steps)
            if "secrets.BOT_PAT" in str(s.get("env", {}).get("GH_TOKEN", ""))
        ]
        assert bot_pat_consumers, f"{workflow}:{job} should consume BOT_PAT"
        assert first_identity < min(bot_pat_consumers), (
            "the identity report must precede the first BOT_PAT API call so "
            "budget exhaustion cannot hide the identity (issue #4607)"
        )
