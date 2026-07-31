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

MATRIX_HEADER = "| Agent | Use For | Avoid When |"

_MATRIX_ROW = re.compile(
    r"^\| \*\*(?P<agent>[^*]+)\*\* \| (?P<use_for>[^|]+) \| (?P<avoid>[^|]+) \|$",
    re.MULTILINE,
)


def _routing_matrix(path: Path) -> dict[str, tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    return {
        match.group("agent"): (
            match.group("use_for").strip().lower(),
            match.group("avoid").strip().lower(),
        )
        for match in _MATRIX_ROW.finditer(text)
    }


def _matrix_block(text: str) -> list[str]:
    """Raw data rows of the capability matrix, header and delimiter excluded."""
    lines = text.split("\n")
    start = lines.index(MATRIX_HEADER)
    block: list[str] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        block.append(line)
    return block


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
    use_for, _avoid = matrix[agent]
    route_text = f"{agent} {use_for} {request}".lower()

    assert all(term in route_text for term in required_terms)
    assert Path(str(AGENT_SURFACES[surface]).format(agent=agent)).is_file()


@pytest.mark.parametrize("surface,path", ORCHESTRATOR_SURFACES.items())
def test_matrix_routes_by_capability_not_by_model(surface: str, path: Path) -> None:
    """The matrix selects an agent; the model comes from the install, not this table.

    A hand-maintained Model column restated frontmatter the build already reads,
    across six byte-parity copies. No column can be right: an installed definition
    may declare a model, and when it declares none the harness supplies its own
    platform default, so one agent resolves differently per install. Measured
    before removal, the column disagreed with 7 of 22 Claude definitions, 13 of 22
    GitHub definitions, and 15 of 22 Copilot CLI and VS Code definitions. This test
    previously pinned three wrong values.
    """
    text = path.read_text(encoding="utf-8")
    matrix = _routing_matrix(path)
    rows = _matrix_block(text)

    assert "Model column" not in text
    assert "| Agent | Use For | Model | Avoid When |" not in text
    assert matrix, f"{surface}: capability matrix parsed zero rows"
    assert len(matrix) == len(rows), (
        f"{surface}: {len(rows)} matrix rows present but {len(matrix)} parsed"
    )
    for agent, (use_for, avoid) in matrix.items():
        assert use_for, f"{surface}: {agent} has an empty Use For cell"
        assert avoid, f"{surface}: {agent} has an empty Avoid When cell"
