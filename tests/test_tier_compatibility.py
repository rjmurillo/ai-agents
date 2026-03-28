"""Tests for agent tier hierarchy validation.

Validates that agent sequences follow correct delegation patterns
as defined in .agents/AGENT-SYSTEM.md Section 2.5.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = str(
    Path(__file__).resolve().parent.parent
    / ".claude"
    / "skills"
    / "workflow"
    / "scripts"
    / "test_tier_compatibility.py"
)


def run_validator(*agents: str) -> subprocess.CompletedProcess:
    """Run the tier compatibility validator with the given agents."""
    return subprocess.run(
        [sys.executable, SCRIPT, *agents],
        capture_output=True,
        text=True,
    )


class TestValidTierSequences:
    """Valid delegation patterns that should pass."""

    def test_expert_to_manager(self):
        result = run_validator("architect", "orchestrator")
        assert result.returncode == 0

    def test_expert_to_builder(self):
        result = run_validator("architect", "implementer")
        assert result.returncode == 0

    def test_expert_to_integration(self):
        result = run_validator("architect", "analyst")
        assert result.returncode == 0

    def test_manager_to_builder(self):
        result = run_validator("orchestrator", "implementer")
        assert result.returncode == 0

    def test_manager_to_integration(self):
        result = run_validator("orchestrator", "analyst")
        assert result.returncode == 0

    def test_builder_to_integration(self):
        result = run_validator("implementer", "analyst")
        assert result.returncode == 0

    def test_same_tier_expert(self):
        result = run_validator("architect", "roadmap")
        assert result.returncode == 0

    def test_same_tier_manager(self):
        result = run_validator("orchestrator", "critic")
        assert result.returncode == 0

    def test_same_tier_builder(self):
        result = run_validator("implementer", "qa", "security")
        assert result.returncode == 0

    def test_same_tier_integration(self):
        result = run_validator("analyst", "explainer")
        assert result.returncode == 0

    def test_multi_tier_expert_manager_builder(self):
        result = run_validator("architect", "orchestrator", "implementer", "qa")
        assert result.returncode == 0

    def test_multi_tier_with_parallel_builders(self):
        result = run_validator(
            "architect", "orchestrator", "implementer", "qa", "security"
        )
        assert result.returncode == 0

    def test_full_hierarchy(self):
        result = run_validator("roadmap", "critic", "implementer", "analyst")
        assert result.returncode == 0


class TestInvalidTierSequences:
    """Invalid delegation patterns that should fail."""

    def test_builder_to_manager(self):
        result = run_validator("implementer", "orchestrator")
        assert result.returncode == 1
        assert "cannot delegate" in result.stdout

    def test_builder_to_expert(self):
        result = run_validator("qa", "architect")
        assert result.returncode == 1
        assert "cannot delegate" in result.stdout

    def test_integration_to_builder(self):
        result = run_validator("analyst", "implementer")
        assert result.returncode == 1
        assert "cannot delegate" in result.stdout

    def test_integration_to_manager(self):
        result = run_validator("explainer", "orchestrator")
        assert result.returncode == 1
        assert "cannot delegate" in result.stdout

    def test_integration_to_expert(self):
        result = run_validator("retrospective", "architect")
        assert result.returncode == 1
        assert "cannot delegate" in result.stdout

    def test_manager_to_expert(self):
        result = run_validator("orchestrator", "architect")
        assert result.returncode == 1
        assert "cannot delegate" in result.stdout

    def test_mixed_invalid_pattern(self):
        result = run_validator("implementer", "orchestrator", "qa")
        assert result.returncode == 1


class TestUnknownAgents:
    """Unknown agent names should fail with exit code 2."""

    def test_unknown_agent(self):
        result = run_validator("unknown-agent")
        assert result.returncode == 2
        assert "Unknown agent" in result.stderr

    def test_unknown_agent_in_sequence(self):
        result = run_validator("architect", "unknown-agent", "implementer")
        assert result.returncode == 2


class TestViolationReporting:
    """Verify violation details are reported correctly."""

    def test_reports_violation_position(self):
        result = run_validator("architect", "implementer", "orchestrator")
        assert result.returncode == 1
        assert "Position 2" in result.stdout


ALL_AGENTS = [
    # Expert
    "high-level-advisor",
    "independent-thinker",
    "architect",
    "roadmap",
    # Manager
    "orchestrator",
    "milestone-planner",
    "critic",
    "issue-feature-review",
    "pr-comment-responder",
    # Builder
    "implementer",
    "qa",
    "devops",
    "security",
    "debug",
    # Integration
    "analyst",
    "explainer",
    "task-decomposer",
    "retrospective",
    "spec-generator",
    "adr-generator",
    "backlog-generator",
    "janitor",
    "memory",
    "skillbook",
    "context-retrieval",
]


@pytest.mark.parametrize("agent", ALL_AGENTS)
def test_recognizes_agent(agent: str):
    """Every known agent should be accepted as a single-element sequence."""
    result = run_validator(agent)
    assert result.returncode == 0


class TestRealWorldWorkflows:
    """Validate real-world agent routing patterns."""

    def test_security_incident(self):
        # Orchestrator coordinates: dispatches builders for remediation,
        # with integration support
        result = run_validator(
            "orchestrator", "security", "devops", "implementer", "qa", "analyst"
        )
        assert result.returncode == 0

    def test_feature_workflow(self):
        # Architect leads: delegates to manager for planning, then builders
        result = run_validator(
            "architect",
            "milestone-planner",
            "critic",
            "implementer",
            "qa",
            "security",
        )
        assert result.returncode == 0

    def test_strategic_decision(self):
        result = run_validator(
            "roadmap",
            "high-level-advisor",
            "architect",
            "orchestrator",
            "implementer",
        )
        assert result.returncode == 0

    def test_documentation(self):
        # Critic (manager) reviews explainer (integration) output
        result = run_validator("critic", "explainer")
        assert result.returncode == 0

    def test_research_peers(self):
        result = run_validator("analyst", "explainer")
        assert result.returncode == 0
