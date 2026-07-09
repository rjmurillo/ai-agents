"""Structural tests for the memory-maintenance sub-skill.

Issue #2925 / ADR-063 (accepted 2026-06-17) decomposes the memory router by
operation. This phase extracts the health-check, token-count, size-validation,
graph-density, and benchmarking maintenance operations into a focused
`memory-maintenance` sub-skill while `memory` remains the thin router. These
tests pin the contract the sub-skill must honor:

- SKILL.md exists with required frontmatter (name, description).
- The skill stays under the 500-line ceiling (.claude/skills/CLAUDE.md).
- The description names the maintenance operations and 3 to 5 backtick triggers.
- The skill points callers at the canonical maintenance scripts (it does not
  reimplement them). The scripts stay in the memory skill tree.
- The skill owns the benchmarking.md and troubleshooting.md references that
  travel with the operation per ADR-063.
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
BENCHMARKING_REFERENCE = SKILL_DIR / "references" / "benchmarking.md"
TROUBLESHOOTING_REFERENCE = SKILL_DIR / "references" / "troubleshooting.md"

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
    assert re.search(r"^name:\s*memory-maintenance\s*$", block, re.MULTILINE), (
        "frontmatter name must be exactly memory-maintenance"
    )
    assert re.search(r"^description:\s*\S", block, re.MULTILINE) or re.search(
        r"^description:\s*[>|]", block, re.MULTILINE
    ), "description required"


def test_skill_under_size_ceiling() -> None:
    # Arrange
    line_count = len(_read_skill().splitlines())

    # Act / Assert
    assert line_count <= 500, f"SKILL.md is {line_count} lines, ceiling is 500"


def test_description_names_maintenance_operations() -> None:
    # Arrange
    block = _frontmatter_block().lower()

    # Act / Assert: the description must name the operations it owns.
    assert "health" in block, "description must name the health-check operation"
    assert "token" in block, "description must name the token-count operation"


def test_description_has_three_to_five_backtick_triggers() -> None:
    # Arrange: SkillForge requires 3 to 5 backtick-wrapped trigger phrases.
    block = _frontmatter_block()
    triggers = _BACKTICK_TRIGGER.findall(block)

    # Act / Assert
    assert 3 <= len(triggers) <= 5, (
        f"expected 3 to 5 backtick trigger phrases, found {len(triggers)}: {triggers}"
    )


def test_points_at_canonical_health_script() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: the sub-skill must route to the canonical script, not
    # reimplement the check. The script stays in the memory skill tree. Assert
    # the shared location fragment and the script name separately so the test
    # does not hard-code the bare .claude/skills path the portability ratchet
    # forbids (check_skill_portability); test_uses_portable_script_root covers
    # the plugin-root invocation form.
    assert "skills/memory/scripts" in body, (
        "memory-maintenance must reference the shared memory scripts directory"
    )
    assert "test_memory_health.py" in body, (
        "memory-maintenance must delegate to the canonical test_memory_health.py"
    )


def test_points_at_canonical_token_script() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: assert the script name only; the shared directory fragment
    # is checked in test_points_at_canonical_health_script and the portable
    # invocation form in test_uses_portable_script_root.
    assert "count_memory_tokens.py" in body, (
        "memory-maintenance must delegate to the canonical count_memory_tokens.py"
    )


def test_uses_portable_script_root() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: executable invocations must resolve the plugin root through
    # the harness env var so a vendored install works (check_skill_md_exec_portability).
    assert "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}" in body, (
        "memory-maintenance must invoke scripts through the portable plugin-root form"
    )


def test_owns_benchmarking_reference() -> None:
    # Arrange / Act / Assert: the reference travels with the operation per
    # ADR-063 (each reference file lives with the sub-skill that invokes it).
    assert BENCHMARKING_REFERENCE.is_file(), (
        f"benchmarking.md must live under {SKILL_DIR / 'references'}"
    )


def test_owns_troubleshooting_reference() -> None:
    # Arrange / Act / Assert
    assert TROUBLESHOOTING_REFERENCE.is_file(), (
        f"troubleshooting.md must live under {SKILL_DIR / 'references'}"
    )


def test_skill_links_to_owned_references() -> None:
    # Arrange
    body = _read_skill()

    # Act / Assert: the SKILL.md must point demand-loaders at its references.
    assert "references/benchmarking.md" in body, (
        "SKILL.md must link to references/benchmarking.md"
    )
    assert "references/troubleshooting.md" in body, (
        "SKILL.md must link to references/troubleshooting.md"
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
    ["health", "token", "benchmark"],
)
def test_carries_maintenance_operation_concepts(term: str) -> None:
    # Arrange: the sub-skill must be a deep module (carry the maintenance
    # knowledge), not a one-line pass-through to the router.
    body = _read_skill().lower()

    # Act / Assert
    assert term in body, f"memory-maintenance must describe the {term!r} concept"
