"""Static contract test for the SPDD REASONS Canvas labels (Issue #1996).

The spec-generator Requirement Structure section must carry R/E/A/S/O/N/S
labels for SPDD (Spec-Driven Development) interop. This test pins each canvas
letter and its label in the canonical SKILL.md and asserts the Copilot CLI
mirror agrees, so a regeneration that drops the labels fails fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _repo_root(start: Path) -> Path:
    """Find the repository root from canonical and generated test locations."""
    for candidate in (start, *start.parents):
        if (candidate / ".claude").is_dir() and (
            candidate / "src" / "copilot-cli"
        ).is_dir():
            return candidate
    raise RuntimeError(f"repository root not found from {start}")


REPO_ROOT = _repo_root(Path(__file__).resolve())
CANONICAL_SKILL = REPO_ROOT / ".claude" / "skills" / "spec-generator" / "SKILL.md"
MIRROR_SKILL = (
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "spec-generator" / "SKILL.md"
)

REASONS_LABELS = (
    "**R (Requirements)**",
    "**E (Entities)**",
    "**A (Approach)**",
    "**S (Structure)**",
    "**O (Operations)**",
    "**N (Norms)**",
    "**S (Safeguards)**",
)


def _requirement_structure_section(text: str) -> str:
    """Return the body of the `### Requirement Structure` section."""
    start = text.index("### Requirement Structure")
    end = text.index("### Design Structure", start)
    return text[start:end]


def test_canonical_skill_declares_reasons_canvas_anchor():
    """The Requirement Structure section names the SPDD REASONS Canvas."""
    section = _requirement_structure_section(
        CANONICAL_SKILL.read_text(encoding="utf-8")
    )
    assert "SPDD REASONS Canvas" in section


@pytest.mark.parametrize("label", REASONS_LABELS)
def test_canonical_skill_has_each_reasons_label(label: str):
    """Each R/E/A/S/O/N/S label appears in the Requirement Structure section."""
    section = _requirement_structure_section(
        CANONICAL_SKILL.read_text(encoding="utf-8")
    )
    assert label in section


def test_canonical_skill_preserves_existing_body_sections():
    """The REASONS labels are additive; existing sections still exist."""
    section = _requirement_structure_section(
        CANONICAL_SKILL.read_text(encoding="utf-8")
    )
    for item in (
        "1. Requirement Statement (EARS format, single behavior)",
        "2. Context",
        "3. Ontology (entities this requirement touches, by canonical name; see below)",
        "4. Acceptance Criteria (checkboxes, each pass/fail testable)",
        "5. Rationale",
        "6. Dependencies",
    ):
        assert item in section


@pytest.mark.parametrize("label", REASONS_LABELS)
def test_copilot_mirror_has_each_reasons_label(label: str):
    """The Copilot CLI mirror carries the same REASONS labels.

    Guards against a mirror regeneration that drops or reorders the labels.
    """
    section = _requirement_structure_section(
        MIRROR_SKILL.read_text(encoding="utf-8")
    )
    assert label in section
