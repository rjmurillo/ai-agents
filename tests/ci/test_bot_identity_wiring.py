"""The bot identity diagnostic is wired where API-heavy work runs.

Issue #4607: the mis-issued ``BOT_PAT`` stayed invisible because no
unconditional step reported the credential's resolved identity. These tests
parse the YAML (never substring-match, per .claude/rules/testing.md MUST 9)
and fail when the step is removed, renamed, or detached from the module.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION_PATH = REPO_ROOT / ".github" / "actions" / "ai-review" / "action.yml"
PR_MAINTENANCE_PATH = REPO_ROOT / ".github" / "workflows" / "pr-maintenance.yml"
MODULE_INVOCATION = "check_bot_identity.py"
EXPECTED_BOT_ID = "250269933"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _identity_steps(steps: list[dict]) -> list[dict]:
    return [step for step in steps if MODULE_INVOCATION in (step.get("run") or "")]


class TestAiReviewAction:
    def test_identity_step_runs_unconditionally_with_bot_pat(self):
        action = _load(ACTION_PATH)

        steps = _identity_steps(action["runs"]["steps"])
        assert len(steps) == 1, "exactly one identity step in the ai-review action"
        step = steps[0]
        assert step["env"]["IDENTITY_TOKEN"] == "${{ inputs.bot-pat }}"
        assert str(step["env"]["EXPECTED_BOT_ID"]) == EXPECTED_BOT_ID
        assert "if" not in step, (
            "the identity step must be unconditional; gating it behind "
            "enable-diagnostics is what hid issue #4607"
        )

    def test_identity_step_is_not_strict_yet(self):
        action = _load(ACTION_PATH)

        step = _identity_steps(action["runs"]["steps"])[0]
        assert "IDENTITY_STRICT" not in step.get("env", {}), (
            "strict mode blocks every run while the secret is still "
            "mis-issued; enable it only after the owner rotates BOT_PAT"
        )


class TestPrMaintenanceWorkflow:
    def test_discover_job_reports_bot_pat_identity(self):
        workflow = _load(PR_MAINTENANCE_PATH)

        steps = _identity_steps(workflow["jobs"]["discover-prs"]["steps"])
        assert len(steps) == 1, "exactly one identity step in discover-prs"
        step = steps[0]
        assert step["env"]["IDENTITY_TOKEN"] == "${{ secrets.BOT_PAT }}"
        assert str(step["env"]["EXPECTED_BOT_ID"]) == EXPECTED_BOT_ID
