"""Structural tests for the memory-reflexion sub-skill.

Issue #1948 / ADR-063 (accepted 2026-06-17) decomposes the memory router by
operation. This phase extracts the Tier 2 episode-extraction and Tier 3
causal-graph-update write path into a focused `memory-reflexion` sub-skill while
`memory` remains the thin router. These tests pin the contract the sub-skill
must honor:

- SKILL.md exists with required frontmatter (name, version, description).
- The skill stays under the 500-line ceiling (.claude/skills/CLAUDE.md).
- The description names the episode and causal operations and 3 to 5 backtick
  triggers.
- The skill points callers at the canonical extract_session_episode.py and
  update_causal_graph.py scripts (it does not reimplement them).
- The skill owns the reflexion-memory.md reference that travels with the
  operation per ADR-063.
- Vendor-install hygiene (issue #1948 AC8 shape): the sub-skill body carries no
  `.agents/`, `.serena/`, or `.github/` path references.

Tests follow Arrange/Act/Assert, one behavior per test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL_DIR / "SKILL.md"
REFLEXION_REFERENCE = SKILL_DIR / "references" / "reflexion-memory.md"

_FRONTMATTER = re.compile(r"(?s)\A---\r?\n(.*?)\r?\n---\r?\n")
_VENDOR_FORBIDDEN = re.compile(r"(?<![\w/])(?:\.agents|\.serena|\.github)/", re.IGNORECASE)
_BACKTICK_TRIGGER = re.compile(r"`[^`]+`")


def _read_skill() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _frontmatter_block() -> str:
    match = _FRONTMATTER.search(_read_skill())
    assert match is not None, "SKILL.md must open with a --- frontmatter block"
    return match.group(1)


def test_skill_md_exists() -> None:
    # Arrange / Act / Assert
    assert SKILL_MD.is_file(), f"missing SKILL.md at {SKILL_MD}"


def test_frontmatter_has_required_fields() -> None:
    # Arrange
    block = _frontmatter_block()

    # Act / Assert
    assert re.search(r"^name:\s*memory-reflexion\s*$", block, re.MULTILINE), (
        "frontmatter name must be exactly memory-reflexion"
    )
    assert re.search(r"^version:\s*\S+", block, re.MULTILINE), "version required"
    assert re.search(r"^description:\s*\S", block, re.MULTILINE) or re.search(
        r"^description:\s*[>|]", block, re.MULTILINE
    ), "description required"


def test_skill_under_size_ceiling() -> None:
    # Arrange
    line_count = len(_read_skill().splitlines())

    # Act / Assert
    assert line_count <= 500, f"SKILL.md is {line_count} lines, ceiling is 500"


def test_description_names_reflexion_operations() -> None:
    # Arrange
    block = _frontmatter_block().lower()

    # Act / Assert: the description must name both write operations it owns.
    assert "episode" in block, "description must name the episode operation"
    assert "causal" in block, "description must name the causal-graph operation"


def test_description_has_three_to_five_backtick_triggers() -> None:
    # Arrange: SkillForge requires 3 to 5 backtick-wrapped trigger phrases.
    block = _frontmatter_block()
    triggers = _BACKTICK_TRIGGER.findall(block)

    # Act / Assert
    assert 3 <= len(triggers) <= 5, (
        f"expected 3 to 5 backtick trigger phrases, found {len(triggers)}: {triggers}"
    )


def test_points_at_canonical_episode_script() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: the sub-skill must route to the canonical script, not
    # reimplement extraction. The script stays in the memory skill tree.
    assert ".claude/skills/memory/scripts/extract_session_episode.py" in body, (
        "memory-reflexion must delegate to the canonical extract_session_episode.py"
    )


def test_points_at_canonical_causal_script() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert
    assert ".claude/skills/memory/scripts/update_causal_graph.py" in body, (
        "memory-reflexion must delegate to the canonical update_causal_graph.py"
    )


def test_owns_reflexion_reference() -> None:
    # Arrange / Act / Assert: the reference travels with the operation per
    # ADR-063 (each reference file lives with the sub-skill that invokes it).
    assert REFLEXION_REFERENCE.is_file(), (
        f"reflexion-memory.md must live under {SKILL_DIR / 'references'}"
    )


def test_skill_links_to_owned_reference() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: the SKILL.md must point demand-loaders at its reference.
    assert "references/reflexion-memory.md" in body, (
        "SKILL.md must link to references/reflexion-memory.md"
    )


def test_no_vendor_forbidden_path_references() -> None:
    # Arrange
    body = _read_skill()

    # Act
    matches = _VENDOR_FORBIDDEN.findall(body)

    # Assert: vendored installs ship without these trees (issue #1948 AC8).
    assert not matches, f"SKILL.md must not reference vendor-excluded trees: {matches}"


@pytest.mark.parametrize(
    "term",
    ["episode", "causal", "completed"],
)
def test_carries_reflexion_operation_concepts(term: str) -> None:
    # Arrange: the sub-skill must be a deep module (carry the reflexion write
    # path knowledge), not a one-line pass-through to the router.
    body = _read_skill().lower()

    # Act / Assert
    assert term in body, f"memory-reflexion must describe the {term!r} concept"
