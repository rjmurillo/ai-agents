"""Structural tests for the memory-gate sub-skill.

Issue #2925 / ADR-063 (accepted 2026-06-17) decomposes the memory router by
operation. This phase extracts the Memory-First Gate (BLOCKING) and the
Chesterton's Fence investigation protocol into a focused `memory-gate` sub-skill
while `memory` remains the thin router. ADR-070 pins the gate as a BLOCKING step;
these tests pin the contract the sub-skill must honor:

- SKILL.md exists with required frontmatter (name, description).
- The skill stays under the 500-line ceiling (.claude/skills/CLAUDE.md).
- The description names the gate operation and 3 to 5 backtick triggers.
- The skill points callers at the canonical search_memory.py script (it does not
  reimplement Tier 1 search).
- The skill owns the agent-integration.md reference that travels with the
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
AGENT_INTEGRATION_REFERENCE = SKILL_DIR / "references" / "agent-integration.md"

_FRONTMATTER = re.compile(r"(?s)\A---\r?\n(.*?)\r?\n---\r?\n")
_VENDOR_FORBIDDEN = re.compile(r"(?<!\w)(?:\.agents|\.serena|\.github)/", re.IGNORECASE)
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
    assert re.search(r"^name:\s*memory-gate\s*$", block, re.MULTILINE), (
        "frontmatter name must be exactly memory-gate"
    )
    assert re.search(r"^description:\s*\S", block, re.MULTILINE) or re.search(
        r"^description:\s*[>|]", block, re.MULTILINE
    ), "description required"


def test_skill_under_size_ceiling() -> None:
    # Arrange
    line_count = len(_read_skill().splitlines())

    # Act / Assert
    assert line_count <= 500, f"SKILL.md is {line_count} lines, ceiling is 500"


def test_description_names_gate_operation() -> None:
    # Arrange
    block = _frontmatter_block().lower()

    # Act / Assert: the description must name the gate and its investigation frame.
    assert "gate" in block, "description must name the gate operation"
    assert "chesterton" in block, "description must name the Chesterton's Fence frame"


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

    # Act / Assert: the gate delegates Tier 1 search to the canonical script; it
    # does not reimplement search. The script stays in the memory skill tree.
    assert ".claude/skills/memory/scripts/search_memory.py" in body, (
        "memory-gate must delegate to the canonical search_memory.py"
    )


def test_uses_portable_script_root() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: executable invocations must resolve the plugin root through
    # the harness env var so a vendored install works (check_skill_md_exec_portability).
    assert "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}" in body, (
        "memory-gate must invoke scripts through the portable plugin-root form"
    )


def test_owns_agent_integration_reference() -> None:
    # Arrange / Act / Assert: the reference travels with the operation per
    # ADR-063 (each reference file lives with the sub-skill that invokes it).
    assert AGENT_INTEGRATION_REFERENCE.is_file(), (
        f"agent-integration.md must live under {SKILL_DIR / 'references'}"
    )


def test_skill_links_to_owned_reference() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: the SKILL.md must point demand-loaders at its reference.
    assert "references/agent-integration.md" in body, (
        "SKILL.md must link to references/agent-integration.md"
    )


def test_no_vendor_forbidden_path_references() -> None:
    # Arrange
    body = _read_skill()

    # Act
    matches = _VENDOR_FORBIDDEN.findall(body)

    # Assert: vendored installs ship without these trees (issue #1948 AC8).
    assert not matches, f"SKILL.md must not reference vendor-excluded trees: {matches}"


def test_vendor_forbidden_regex_matches_slash_prefixed_paths() -> None:
    # Arrange / Act / Assert: paths can appear after a slash in prose examples.
    forbidden_path = "/" + "." + "agents" + "/session.json"
    assert _VENDOR_FORBIDDEN.search(f"Do not write {forbidden_path}")


@pytest.mark.parametrize(
    "term",
    ["blocking", "chesterton", "investigation"],
)
def test_carries_gate_operation_concepts(term: str) -> None:
    # Arrange: the sub-skill must be a deep module (carry the gate enforcement
    # knowledge), not a one-line pass-through to the router.
    body = _read_skill().lower()

    # Act / Assert
    assert term in body, f"memory-gate must describe the {term!r} concept"
