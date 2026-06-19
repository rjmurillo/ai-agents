"""Structural tests for the memory-search sub-skill.

Phase 1 of issue #1948 / ADR-063 (accepted 2026-06-17) extracts the Tier 1
search operation into a focused `memory-search` sub-skill while `memory`
remains the thin router. These tests pin the contract the sub-skill must honor:

- SKILL.md exists with required frontmatter (name, version, description).
- The skill stays under the 500-line ceiling (.claude/skills/CLAUDE.md).
- The description names the search operation and 3 to 5 backtick triggers.
- The skill points callers at the canonical search_memory.py script.
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
    assert re.search(r"^name:\s*memory-search\s*$", block, re.MULTILINE), (
        "frontmatter name must be exactly memory-search"
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


def test_description_names_search_operation() -> None:
    # Arrange
    block = _frontmatter_block().lower()

    # Act / Assert
    assert "search" in block, "description must name the search operation"


def test_description_has_three_to_five_backtick_triggers() -> None:
    # Arrange: SkillForge requires 3 to 5 backtick-wrapped trigger phrases.
    block = _frontmatter_block()
    triggers = _BACKTICK_TRIGGER.findall(block)

    # Act / Assert
    assert 3 <= len(triggers) <= 5, (
        f"expected 3 to 5 backtick trigger phrases, found {len(triggers)}: {triggers}"
    )


def test_points_at_canonical_search_script() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: the sub-skill must route to the canonical script, not
    # reimplement search. The script stays in the memory skill tree.
    assert ".claude/skills/memory/scripts/search_memory.py" in body, (
        "memory-search must delegate to the canonical search_memory.py"
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
    ["progressive disclosure", "serena", "forgetful"],
)
def test_carries_search_operation_concepts(term: str) -> None:
    # Arrange: the sub-skill must be a deep module (carry the search operation
    # knowledge), not a one-line pass-through to the router.
    body = _read_skill().lower()

    # Act / Assert
    assert term in body, f"memory-search must describe the {term!r} concept"
