"""Regression test for the backlog-generator retirement (issue #5701).

The generator does not delete an orphan output when its template disappears,
so this test checks the generated and installed inventories directly. It
asserts the retired agent is absent from every agent tree, from the
orchestrator routing tables, and from the generated catalog, while surviving
agents remain present.

The historical eval spike under ``evals/backlog-generator-spike/`` is kept on
purpose and is not checked here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RETIRED = "backlog-generator"
SURVIVORS = ("orchestrator", "analyst", "task-decomposer", "implementer")

AGENT_TREES = {
    "template": (REPO_ROOT / "templates" / "agents", "{agent}.shared.md"),
    "claude-install": (REPO_ROOT / ".claude" / "agents", "{agent}.md"),
    "github-install": (REPO_ROOT / ".github" / "agents", "{agent}.agent.md"),
    "src-claude": (REPO_ROOT / "src" / "claude" / "agents", "{agent}.md"),
    "copilot-cli": (REPO_ROOT / "src" / "copilot-cli" / "agents", "{agent}.agent.md"),
    "vscode": (REPO_ROOT / "src" / "vs-code-agents", "{agent}.agent.md"),
}

ORCHESTRATOR_COPIES = (
    "templates/agents/orchestrator.shared.md",
    "templates/agents/partials/orchestrator-core-behavior.mustache",
    ".claude/agents/orchestrator.md",
    ".github/agents/orchestrator.agent.md",
    "src/claude/agents/orchestrator.md",
    "src/copilot-cli/agents/orchestrator.agent.md",
    "src/vs-code-agents/orchestrator.agent.md",
)


@pytest.mark.parametrize("tree", sorted(AGENT_TREES))
def test_retired_agent_absent_from_tree(tree: str) -> None:
    directory, _ = AGENT_TREES[tree]
    assert directory.is_dir(), f"{tree} directory missing: {directory}"
    leftovers = sorted(p.name for p in directory.rglob(f"*{RETIRED}*"))
    assert leftovers == [], f"{tree} still ships retired agent files: {leftovers}"


@pytest.mark.parametrize("agent", SURVIVORS)
@pytest.mark.parametrize("tree", sorted(AGENT_TREES))
def test_surviving_agent_present_in_tree(tree: str, agent: str) -> None:
    directory, pattern = AGENT_TREES[tree]
    assert (directory / pattern.format(agent=agent)).is_file()


@pytest.mark.parametrize("relative", ORCHESTRATOR_COPIES)
def test_orchestrator_routing_omits_retired_agent(relative: str) -> None:
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    assert RETIRED not in text
    assert "task-decomposer" in text


def test_generated_catalog_omits_retired_agent() -> None:
    text = (REPO_ROOT / "docs" / "agent-catalog.md").read_text(encoding="utf-8")
    assert RETIRED not in text
    assert "orchestrator" in text


def test_agent_partials_omit_retired_agent() -> None:
    partials = REPO_ROOT / "templates" / "agents" / "partials"
    assert list(partials.glob(f"*{RETIRED}*")) == []
