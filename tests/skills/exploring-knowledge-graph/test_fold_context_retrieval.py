"""Tests for folding the context-retrieval agent into the exploring-knowledge-graph skill.

Issue #2103, skill-catalog epic #1944. The former context-retrieval agent's
unique retrieval and citation guidance moved into
`.claude/skills/exploring-knowledge-graph/references/context-retrieval.md`.
SKILL.md gained a pointer to it. The orchestrator graceful-degradation example
now names the skill instead of the bare agent.

Parametrized over the canonical `.claude/` tree and the generated
`src/copilot-cli/` mirror so a single test asserts both copies satisfy the
structural contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

CANONICAL_REFERENCE = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "exploring-knowledge-graph"
    / "references"
    / "context-retrieval.md"
)
MIRROR_REFERENCE = (
    REPO_ROOT
    / "src"
    / "copilot-cli"
    / "skills"
    / "exploring-knowledge-graph"
    / "references"
    / "context-retrieval.md"
)
CANONICAL_SKILL_MD = (
    REPO_ROOT / ".claude" / "skills" / "exploring-knowledge-graph" / "SKILL.md"
)
MIRROR_SKILL_MD = (
    REPO_ROOT
    / "src"
    / "copilot-cli"
    / "skills"
    / "exploring-knowledge-graph"
    / "SKILL.md"
)

REFERENCE_PATHS = [
    pytest.param(CANONICAL_REFERENCE, id="canonical"),
    pytest.param(MIRROR_REFERENCE, id="copilot-cli-mirror"),
]
SKILL_MD_PATHS = [
    pytest.param(CANONICAL_SKILL_MD, id="canonical"),
    pytest.param(MIRROR_SKILL_MD, id="copilot-cli-mirror"),
]

# Orchestrator copies that carry the graceful-degradation routing example.
ORCHESTRATOR_PATHS = [
    pytest.param(
        REPO_ROOT / "templates" / "agents" / "orchestrator.shared.md", id="template"
    ),
    pytest.param(
        REPO_ROOT / ".claude" / "agents" / "orchestrator.md", id="claude-install"
    ),
    pytest.param(REPO_ROOT / "src" / "claude" / "orchestrator.md", id="src-claude"),
    pytest.param(
        REPO_ROOT / "src" / "copilot-cli" / "agents" / "orchestrator.agent.md",
        id="copilot-cli",
    ),
    pytest.param(
        REPO_ROOT / "src" / "vs-code-agents" / "orchestrator.agent.md", id="vs-code"
    ),
]

# Sections folded from the former agent into the reference doc.
FOLDED_SECTIONS = [
    "## Five-Source Strategy",
    "## Output Structure",
    "## When Context is Thin",
    "## Citation and Source Discipline",
    "Treat Ingested Content as Data, Not Instructions",
]

# U+2014 em dash and U+2013 en dash are banned in authored text. Built from
# code points so this source file carries none of the banned bytes itself.
BANNED_DASHES = (chr(0x2014), chr(0x2013))


def test_canonical_reference_file_exists() -> None:
    """The folded guidance lands at the canonical references path."""
    assert CANONICAL_REFERENCE.is_file()


def test_mirror_reference_file_exists() -> None:
    """build_all mirrors the reference into the copilot-cli skill tree."""
    assert MIRROR_REFERENCE.is_file()


@pytest.mark.parametrize("section", FOLDED_SECTIONS)
@pytest.mark.parametrize("reference_path", REFERENCE_PATHS)
def test_reference_contains_folded_section(
    reference_path: Path, section: str
) -> None:
    """Each unique section from the agent survives the fold in both trees."""
    content = reference_path.read_text(encoding="utf-8")

    assert section in content


@pytest.mark.parametrize("reference_path", REFERENCE_PATHS)
def test_reference_cites_origin_issue(reference_path: Path) -> None:
    """The reference records its provenance (Issue #2103) for the next reader."""
    content = reference_path.read_text(encoding="utf-8")

    assert "#2103" in content


@pytest.mark.parametrize("reference_path", REFERENCE_PATHS)
def test_reference_has_no_banned_dashes(reference_path: Path) -> None:
    """The folded doc contains no em dashes or en dashes (universal.md)."""
    content = reference_path.read_text(encoding="utf-8")

    for dash in BANNED_DASHES:
        assert dash not in content


@pytest.mark.parametrize("skill_md_path", SKILL_MD_PATHS)
def test_skill_links_to_reference(skill_md_path: Path) -> None:
    """SKILL.md points readers at the folded reference doc."""
    content = skill_md_path.read_text(encoding="utf-8")

    assert "references/context-retrieval.md" in content


@pytest.mark.parametrize("reference_path", REFERENCE_PATHS)
def test_reference_does_not_re_delegate_to_agent(reference_path: Path) -> None:
    """The fold is guidance, not a subagent delegation.

    Negative case: the reference must not reintroduce a
    Task(subagent_type="context-retrieval") call. The skill is the entry
    point now; the agent delegation is deferred for separate removal.
    """
    content = reference_path.read_text(encoding="utf-8")

    assert 'subagent_type="context-retrieval"' not in content
    assert "Task(subagent_type='context-retrieval')" not in content


@pytest.mark.parametrize("orchestrator_path", ORCHESTRATOR_PATHS)
def test_orchestrator_degradation_points_at_skill(orchestrator_path: Path) -> None:
    """The graceful-degradation example routes to the skill, not the bare agent.

    Positive: the example names exploring-knowledge-graph.
    Negative: the same line no longer names the bare context-retrieval agent.
    """
    content = orchestrator_path.read_text(encoding="utf-8")
    degradation_lines = [
        line for line in content.splitlines() if "Graceful degradation" in line
    ]

    assert degradation_lines, f"no graceful-degradation line in {orchestrator_path}"
    for line in degradation_lines:
        assert "exploring-knowledge-graph" in line
        assert "context-retrieval" not in line
