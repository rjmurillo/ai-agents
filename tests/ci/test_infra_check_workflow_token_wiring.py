"""Verify the quality-gate workflow passes github-token to check-agent-infrastructure."""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AI_PR_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ai-pr-quality-gate.yml"


class TestInfraCheckWorkflowTokenWiring:
    """Verify the quality-gate workflow passes github-token to check-agent-infrastructure."""

    def test_quality_gate_passes_github_token_to_check_agent_infrastructure(self) -> None:
        workflow = yaml.safe_load(_AI_PR_WORKFLOW.read_text(encoding="utf-8"))
        infra_steps = []
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                if str(step.get("uses", "")).endswith("check-agent-infrastructure"):
                    infra_steps.append(step)

        assert len(infra_steps) >= 1, "Expected at least one check-agent-infrastructure step"
        for step in infra_steps:
            assert "github-token" in step.get("with", {}), (
                f"Step {step.get('name', 'unnamed')} missing github-token input"
            )
