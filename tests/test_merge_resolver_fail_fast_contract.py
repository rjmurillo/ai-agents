"""Prompt-contract regression test for the merge-resolver fail-fast contract.

Issue #2646: during a pr-autofix run the merge-resolver agent returned a long
resolution plan and marked execution phases complete, but it had no shell
(Bash/worktree/git/push) capability and never actually merged. It reported the
plan as if it were completed work.

The fix adds a fail-fast execution-capability precondition to the agent prompt
and the skill: if shell execution is unavailable, return BLOCKED before any
analysis that reads as completion, and route execution back to the orchestrator.
A plan is never a completion: an execution phase is only complete when a tool
result in the same run proves it ran.

This test pins that contract across the shared template, generated platform
copies, installed agent copies, the hand-maintained Claude source, and the skill.
That prevents a future edit, manual sync, or regeneration from silently dropping
it. If a platform path is added or removed, update ``AGENT_PATHS``.

Pytest controls this file's process exit code.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The shared template generates VS Code and Copilot CLI source copies via
# build/generate_agents.py. src/claude/merge-resolver.md is hand-maintained per
# src/claude/AGENTS.md. The .claude and .github installed copies are
# hand-maintained install siblings and must be synced manually.
AGENT_PATHS: tuple[Path, ...] = (
    REPO_ROOT / "templates/agents/merge-resolver.shared.md",
    REPO_ROOT / ".claude/agents/merge-resolver.md",
    REPO_ROOT / ".github/agents/merge-resolver.agent.md",
    REPO_ROOT / "src/claude/merge-resolver.md",
    REPO_ROOT / "src/copilot-cli/agents/merge-resolver.agent.md",
    REPO_ROOT / "src/vs-code-agents/merge-resolver.agent.md",
)

SKILL_PATH = REPO_ROOT / ".claude/skills/merge-resolver/SKILL.md"

# Stable markers the fail-fast contract must carry. Each is a distinct
# behavioral requirement from issue #2646; matching is case-insensitive on the
# rendered text so heading-case normalization does not break the assertion.
PRECONDITION_HEADING = "execution capability precondition"
PHASE_1_HEADING = "phase 1: context gathering"
BLOCKED_FAIL_FAST = "return immediately with status [blocked]"
NO_PLAN_AS_COMPLETION = "a plan is not a completion"
ROUTE_BACK_TO_ORCHESTRATOR = "route execution back to the orchestrator"
TOOL_RESULT_PROOF = "tool result in this run"


def _read(path: Path) -> str:
    assert path.exists(), f"Expected file at {path.relative_to(REPO_ROOT)}"
    return path.read_text(encoding="utf-8").lower()


@pytest.mark.parametrize(
    "path",
    (*AGENT_PATHS, SKILL_PATH),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_carries_execution_capability_precondition(path: Path) -> None:
    """The fail-fast precondition heading appears before any merge work."""
    text = _read(path)
    precondition_index = text.find(PRECONDITION_HEADING)
    phase_1_index = text.find(PHASE_1_HEADING)
    assert precondition_index >= 0, (
        f"{path.relative_to(REPO_ROOT)} is missing the execution-capability "
        "precondition heading (issue #2646)"
    )
    assert phase_1_index >= 0, (
        f"{path.relative_to(REPO_ROOT)} is missing the Phase 1 context heading "
        "(issue #2646)"
    )
    assert precondition_index < phase_1_index, (
        f"{path.relative_to(REPO_ROOT)} must place the execution-capability "
        "precondition before Phase 1 merge work (issue #2646)"
    )


@pytest.mark.parametrize(
    "path",
    (*AGENT_PATHS, SKILL_PATH),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_precondition_returns_blocked(path: Path) -> None:
    """No-shell path must return a BLOCKED status, not a plan."""
    text = _read(path)
    assert BLOCKED_FAIL_FAST in text, (
        f"{path.relative_to(REPO_ROOT)} must instruct returning immediately with "
        "status [BLOCKED] when shell execution is unavailable (issue #2646)"
    )


@pytest.mark.parametrize(
    "path",
    (*AGENT_PATHS, SKILL_PATH),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_no_plan_as_completion(path: Path) -> None:
    """A plan must never be reported as completed execution work."""
    text = _read(path)
    assert NO_PLAN_AS_COMPLETION in text, (
        f"{path.relative_to(REPO_ROOT)} must state that a plan is not a "
        "completion (issue #2646)"
    )


@pytest.mark.parametrize(
    "path",
    (*AGENT_PATHS, SKILL_PATH),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_routes_back_to_orchestrator(path: Path) -> None:
    """When it cannot execute, route execution back to the orchestrator."""
    text = _read(path)
    assert ROUTE_BACK_TO_ORCHESTRATOR in text, (
        f"{path.relative_to(REPO_ROOT)} must route execution back to the "
        "orchestrator when it cannot execute (issue #2646)"
    )


@pytest.mark.parametrize(
    "path",
    (*AGENT_PATHS, SKILL_PATH),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_completion_requires_tool_result(path: Path) -> None:
    """An execution phase is complete only when a tool result proves it ran."""
    text = _read(path)
    assert TOOL_RESULT_PROOF in text, (
        f"{path.relative_to(REPO_ROOT)} must require a tool result in this run "
        "to mark an execution phase complete (issue #2646)"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
