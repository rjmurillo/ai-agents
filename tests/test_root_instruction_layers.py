"""Root instruction files retain routing while avoiding duplicate catalogs."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_agents_retains_shared_routing_and_gates() -> None:
    text = _text("AGENTS.md")
    for required in (
        "## Retrieval",
        "## Gates",
        "## Boundaries",
        "## Skill-First",
        "## Standards",
        "session-init",
        "ai-agents-portability-campaign",
        "## Stack",
        "Claude honors `paths`",
    ):
        assert required in text
    assert "when one exists" in text
    assert "not blocking" in text
    assert "## Context" in text
    assert "Tests: `uv run pytest" not in text


def test_claude_imports_agents_and_retains_claude_routes() -> None:
    text = _text("CLAUDE.md")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    assert lines[:2] == ["# Claude Code Instructions", "@AGENTS.md"]
    for required in (
        "orchestrator",
        "/autoplan",
        "paths",
        "legacy keys that load unconditionally",
        "weekly retros",
    ):
        assert required in text
    assert "Installation Locations" not in text
    assert "For non-trivial tasks: `Task(" not in text
    assert "Memory Interface Decision Matrix" not in text
    assert "## Lifecycle commands" not in text


def test_copilot_retains_routes_without_duplicate_catalogs() -> None:
    text = _text(".github/copilot-instructions.md")
    for required in (
        "`AGENTS.md`",
        "/agent",
        "#runSubagent",
        "loads root `AGENTS.md` automatically",
    ):
        assert required in text
    for duplicate in (
        "## Serena MCP Initialization",
        "## Critical Constraints",
        "## Session Protocol",
        "## Gotchas",
        "## Key Documents",
        "**Why delegate:**",
        "**Delegation pattern:**",
    ):
        assert duplicate not in text
