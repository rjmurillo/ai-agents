"""Verify the quality-gate workflow passes github-token to check-agent-infrastructure."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AI_PR_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ai-pr-quality-gate.yml"
_EXPECTED_TOKEN = "${{ secrets.GITHUB_TOKEN }}"


def _infra_steps(workflow: dict) -> list[dict]:
    """Return all steps that use check-agent-infrastructure."""
    steps = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if str(step.get("uses", "")).endswith("check-agent-infrastructure"):
                steps.append(step)
    return steps


class TestInfraCheckWorkflowTokenWiring:
    """Verify the quality-gate workflow passes the runner token to check-agent-infrastructure."""

    def test_quality_gate_passes_runner_token_to_check_agent_infrastructure(self) -> None:
        workflow = yaml.safe_load(_AI_PR_WORKFLOW.read_text(encoding="utf-8"))
        steps = _infra_steps(workflow)

        assert len(steps) >= 1, "Expected at least one check-agent-infrastructure step"
        for step in steps:
            actual = step.get("with", {}).get("github-token")
            assert actual == _EXPECTED_TOKEN, (
                f"Step '{step.get('name', 'unnamed')}': "
                f"expected github-token={_EXPECTED_TOKEN!r}, got {actual!r}"
            )

    @pytest.mark.parametrize(
        "label, mutated_with",
        [
            ("missing", {}),
            ("empty", {"github-token": ""}),
            ("null", {"github-token": None}),
            ("bot-pat", {"github-token": "${{ secrets.BOT_PAT }}"}),
        ],
        ids=["missing", "empty", "null", "bot-pat"],
    )
    def test_rejects_incorrect_github_token_value(
        self, label: str, mutated_with: dict
    ) -> None:
        workflow = yaml.safe_load(_AI_PR_WORKFLOW.read_text(encoding="utf-8"))
        steps = _infra_steps(workflow)
        assert len(steps) >= 1, "Precondition: at least one infra step exists"

        step = steps[0]
        original_with = step.get("with", {}).copy()
        step["with"] = {**original_with, **mutated_with} if mutated_with else {
            k: v for k, v in original_with.items() if k != "github-token"
        }

        actual = step.get("with", {}).get("github-token")
        assert actual != _EXPECTED_TOKEN, (
            f"Negative case '{label}' should not match the expected token"
        )
