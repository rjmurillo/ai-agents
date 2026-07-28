"""Regression tests for quality-auditor agent reachability across installs."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

QUALITY_AUDITOR_SURFACES = {
    "template": REPO_ROOT / "templates" / "agents" / "quality-auditor.shared.md",
    "github-install": REPO_ROOT / ".github" / "agents" / "quality-auditor.agent.md",
    "src-claude": REPO_ROOT / "src" / "claude" / "quality-auditor.md",
    "copilot-cli": REPO_ROOT / "src" / "copilot-cli" / "agents" / "quality-auditor.agent.md",
    "vscode": REPO_ROOT / "src" / "vs-code-agents" / "quality-auditor.agent.md",
}

ORCHESTRATOR_SURFACES = {
    "template": REPO_ROOT / "templates" / "agents" / "orchestrator.shared.md",
    "github-install": REPO_ROOT / ".github" / "agents" / "orchestrator.agent.md",
    "src-claude": REPO_ROOT / "src" / "claude" / "orchestrator.md",
    "copilot-cli": REPO_ROOT / "src" / "copilot-cli" / "agents" / "orchestrator.agent.md",
    "vscode": REPO_ROOT / "src" / "vs-code-agents" / "orchestrator.agent.md",
}

_QUALITY_ROUTE_ROW = re.compile(
    r"^\| \*\*quality-auditor\*\* \|",
    re.MULTILINE,
)


@pytest.mark.parametrize("surface,path", QUALITY_AUDITOR_SURFACES.items())
def test_quality_auditor_agent_exists_in_each_install_surface(
    surface: str,
    path: Path,
) -> None:
    """Each shipped agent surface has a concrete quality-auditor prompt."""
    assert path.is_file(), f"{surface} is missing {path.relative_to(REPO_ROOT)}"


@pytest.mark.parametrize("surface,path", QUALITY_AUDITOR_SURFACES.items())
def test_quality_auditor_agent_contains_invokable_grading_contract(
    surface: str,
    path: Path,
) -> None:
    """Each quality-auditor prompt routes to the grading script it tells agents to run."""
    text = path.read_text(encoding="utf-8")
    assert "# Quality Auditor Agent" in text, surface
    assert "uv run python .claude/skills/quality-grades/scripts/grade_domains.py" in text, surface


@pytest.mark.parametrize("surface,path", ORCHESTRATOR_SURFACES.items())
def test_orchestrator_quality_auditor_route_resolves_to_installed_agent(
    surface: str,
    path: Path,
) -> None:
    """Every orchestrator surface that routes to quality-auditor has that agent installed."""
    text = path.read_text(encoding="utf-8")
    assert _QUALITY_ROUTE_ROW.search(text), surface
    assert QUALITY_AUDITOR_SURFACES[surface].is_file(), surface
