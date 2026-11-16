"""Committed host trees for the split-agent reference roots and checkout clause.

Each host tree must carry the form its probe supports, and every checkout path the
clause names must exist in this repository.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from split_reference_helpers import (
    AGENT_SKILL,
    CURSOR_TREE,
    FALLBACK_TREES,
    REPO_ROOT,
    SPLIT_AGENTS,
    ref,
    split_agent_files,
)

# isort: split

import agent_tree_copy as atc
from generate_agents_common import (
    CHECKOUT_CLAUSE,
    CLAUDE_ROOT,
    COPILOT_ROOT,
    MARKER_DECLARATION,
    SHARED_ROOT,
    SPLIT_REFERENCE_SKILLS,
)


@pytest.mark.parametrize(
    ("platform", "expected"), [("cursor", True), ("codex", False), ("muse", False)]
)
def test_platform_config_sets_reference_root_per_host(platform: str, expected: bool) -> None:
    config = REPO_ROOT / "templates" / "platforms" / f"{platform}.yaml"
    stanza = atc._read_stanza(config)

    assert stanza is not None
    assert (stanza.get(atc.KEEP_ROOT_KEY) is True) is expected


@pytest.mark.parametrize("tree", ["claude", "copilot-cli", "cursor", "codex", "muse"])
def test_every_split_skill_ships_a_references_folder_in_each_host_tree(tree: str) -> None:
    missing = [
        skill
        for skill in SPLIT_REFERENCE_SKILLS
        if not (REPO_ROOT / "src" / tree / "skills" / skill / "references").is_dir()
    ]

    assert missing == []


def test_cursor_agents_carry_the_bare_claude_reference_root() -> None:
    found = [
        path.name
        for path in split_agent_files(CURSOR_TREE)
        for skill in SPLIT_REFERENCE_SKILLS
        if ref(CLAUDE_ROOT, skill) in path.read_text(encoding="utf-8")
    ]
    nested = [
        path.name
        for path in split_agent_files(CURSOR_TREE)
        for skill in SPLIT_REFERENCE_SKILLS
        if ref(SHARED_ROOT, skill) in path.read_text(encoding="utf-8")
    ]

    assert sorted(found) == [
        "architect.md",
        "critic.md",
        "implementer.md",
        "orchestrator.md",
        "qa.md",
    ]
    assert nested == []


@pytest.mark.parametrize("tree", FALLBACK_TREES)
def test_fallback_host_agents_carry_no_bare_claude_reference_root(tree: str) -> None:
    files = split_agent_files(tree)
    shared = [
        path.name
        for path in files
        for skill in SPLIT_REFERENCE_SKILLS
        if ref(SHARED_ROOT, skill) in path.read_text(encoding="utf-8")
    ]
    offenders = [
        f"{path.relative_to(REPO_ROOT).as_posix()}: {skill}"
        for path in files
        for skill in SPLIT_REFERENCE_SKILLS
        if ref(CLAUDE_ROOT, skill) in path.read_text(encoding="utf-8")
    ]

    clauses = [path.name for path in files if "In a checkout that loads" in path.read_text("utf-8")]

    assert offenders == []
    assert len(shared) == 5, shared
    assert clauses == []


@pytest.mark.parametrize(
    ("pattern", "host_root"),
    [
        ("src/claude/agents/{}.md", CLAUDE_ROOT),
        ("src/copilot-cli/agents/{}.agent.md", COPILOT_ROOT),
    ],
    ids=["claude", "copilot-cli"],
)
@pytest.mark.parametrize("agent", SPLIT_AGENTS)
def test_host_render_carries_its_own_reference_root(
    pattern: str, host_root: str, agent: str
) -> None:
    text = (REPO_ROOT / pattern.format(agent)).read_text(encoding="utf-8")

    assert any(ref(host_root, skill) in text for skill in SPLIT_REFERENCE_SKILLS), agent
    assert not any(ref(SHARED_ROOT, skill) in text for skill in SPLIT_REFERENCE_SKILLS), agent


@pytest.mark.parametrize(
    ("pattern", "host_root"),
    [
        ("src/claude/agents/{}.md", CLAUDE_ROOT),
        ("src/copilot-cli/agents/{}.agent.md", COPILOT_ROOT),
        ("src/cursor/agents/{}.md", CLAUDE_ROOT),
    ],
    ids=["claude", "copilot-cli", "cursor"],
)
@pytest.mark.parametrize("agent", SPLIT_AGENTS)
def test_bare_root_render_names_the_checkout_path(pattern: str, host_root: str, agent: str) -> None:
    path = REPO_ROOT / pattern.format(agent)
    if "cursor" in pattern and agent == "security":
        assert not path.exists()  # Cursor ships no security agent (ADR-115 Decision 3).
        return
    skill = AGENT_SKILL[agent]
    expected = f"`{ref(host_root, skill)}`." + CHECKOUT_CLAUSE.format(skill=skill)

    assert path.read_text(encoding="utf-8").count(expected) == 1


@pytest.mark.parametrize("agent", SPLIT_AGENTS)
def test_vs_code_render_keeps_nested_form_without_clause(agent: str) -> None:
    text = (REPO_ROOT / f"src/vs-code-agents/{agent}.agent.md").read_text(encoding="utf-8")

    assert f"`{ref(SHARED_ROOT, AGENT_SKILL[agent])}`." in text
    assert "In a checkout that loads" not in text


@pytest.mark.parametrize("skill", SPLIT_REFERENCE_SKILLS)
def test_checkout_path_named_by_the_clause_holds_reference_files(skill: str) -> None:
    folder = REPO_ROOT / ".claude" / "skills" / skill / "references"

    assert folder.is_dir(), folder
    assert sorted(folder.glob("*.md")), folder


def test_agent_skill_map_covers_the_shared_skill_list() -> None:
    assert sorted(AGENT_SKILL.values()) == sorted(SPLIT_REFERENCE_SKILLS)


def test_copilot_implementer_marker_declares_the_checkout_path() -> None:
    text = (REPO_ROOT / "src/copilot-cli/agents/implementer.agent.md").read_text("utf-8")
    vs_code = (REPO_ROOT / "src/vs-code-agents/implementer.agent.md").read_text("utf-8")

    assert MARKER_DECLARATION.format(skill="build") in text
    assert "Checkout fallback path" not in vs_code
