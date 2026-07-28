"""Regression tests for orchestrator agent routing matrix reachability."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

ORCHESTRATOR_SURFACES = {
    "template": REPO_ROOT / "templates" / "agents" / "orchestrator.shared.md",
    "claude-install": REPO_ROOT / ".claude" / "agents" / "orchestrator.md",
    "github-install": REPO_ROOT / ".github" / "agents" / "orchestrator.agent.md",
    "src-claude": REPO_ROOT / "src" / "claude" / "orchestrator.md",
    "copilot-cli": REPO_ROOT / "src" / "copilot-cli" / "agents" / "orchestrator.agent.md",
    "vscode": REPO_ROOT / "src" / "vs-code-agents" / "orchestrator.agent.md",
}

AGENT_SURFACES = {
    "template": REPO_ROOT / "templates" / "agents" / "{agent}.shared.md",
    "claude-install": REPO_ROOT / ".claude" / "agents" / "{agent}.md",
    "github-install": REPO_ROOT / ".github" / "agents" / "{agent}.agent.md",
    "src-claude": REPO_ROOT / "src" / "claude" / "{agent}.md",
    "copilot-cli": REPO_ROOT / "src" / "copilot-cli" / "agents" / "{agent}.agent.md",
    "vscode": REPO_ROOT / "src" / "vs-code-agents" / "{agent}.agent.md",
}

ROUTING_SCENARIOS = {
    "backlog-generator": (
        "Scan the repo and propose backlog work for unowned quality gaps.",
        ("backlog", "discovery"),
    ),
    "debug": (
        "Debug a runtime failure where the app crashes after startup.",
        ("runtime", "bug"),
    ),
    "dependency-auditor": (
        "Audit dependency CVEs and package health before release.",
        ("dependency", "cves", "package"),
    ),
    "pr-test-analyzer": (
        "Review this PR for missing behavioral test coverage.",
        ("pr", "test", "coverage"),
    ),
    "silent-failure-hunter": (
        "Find swallowed exceptions and unsafe fallback behavior.",
        ("error", "suppression", "fallbacks"),
    ),
}

_MATRIX_ROW = re.compile(
    r"^\| \*\*(?P<agent>[^*]+)\*\* \| (?P<use_for>[^|]+) "
    r"\| (?P<model>[^|]+) \| (?P<avoid>[^|]+) \|$",
    re.MULTILINE,
)


def _routing_matrix(path: Path) -> dict[str, tuple[str, str, str]]:
    text = path.read_text(encoding="utf-8")
    return {
        match.group("agent"): (
            match.group("use_for").strip().lower(),
            match.group("model").strip().lower(),
            match.group("avoid").strip().lower(),
        )
        for match in _MATRIX_ROW.finditer(text)
    }


@pytest.mark.parametrize("surface,path", ORCHESTRATOR_SURFACES.items())
@pytest.mark.parametrize("agent,scenario", ROUTING_SCENARIOS.items())
def test_realistic_request_resolves_to_installed_agent(
    surface: str,
    path: Path,
    agent: str,
    scenario: tuple[str, tuple[str, ...]],
) -> None:
    """A realistic request has a concrete row and installed prompt."""
    request, required_terms = scenario
    matrix = _routing_matrix(path)
    use_for, model, _avoid = matrix[agent]
    route_text = f"{agent} {use_for} {request}".lower()

    assert model == "sonnet"
    assert all(term in route_text for term in required_terms)
    assert Path(str(AGENT_SURFACES[surface]).format(agent=agent)).is_file()
