"""Tests for the Co-change checklist template in .claude/commands/spec.md.

Pins REQ-009-04 and REQ-009-05: Step 6 of the /spec command must include
a `## Co-change checklist` template that the spec-generator emits when
the requirement touches a shared token at more than one site. The
template exists to prevent the PR #1965 verdict-token cascade (3 commits
per token, discovered one site at a time through bot review).

The test is structural, not behavioral. The template is consumed by an
LLM-driven agent (spec-generator), not by code. Structural verification
asserts the template fragments are present and well-formed; behavioral
checks for emitted REQ-NNN files belong in spec-generator's own test
suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / ".claude" / "commands" / "spec.md"


@pytest.fixture(scope="module")
def spec_text() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def step_6_region(spec_text: str) -> str:
    """Return the substring covering Step 6 of /spec.

    Step 6 begins with the numbered ordered-list item `6. **Formalize the
    PRD into durable artifacts**:` and ends at the next top-level item
    (`7.`) or the next major section (`## ...`), whichever comes first.
    """
    start_marker = "6. **Formalize the PRD into durable artifacts**"
    start = spec_text.find(start_marker)
    assert start != -1, "Step 6 anchor not found in spec.md"
    # End at the next numbered step or the next ## section.
    end_candidates = [
        spec_text.find("\n7.", start),
        spec_text.find("\n## ", start),
    ]
    end_candidates = [c for c in end_candidates if c != -1]
    assert end_candidates, "Step 6 has no terminator"
    return spec_text[start : min(end_candidates)]


def test_co_change_checklist_header_present(step_6_region: str) -> None:
    """REQ-009-04 AC: Step 6 must contain `Co-change checklist` template header."""
    assert "## Co-change checklist" in step_6_region, (
        "Step 6 of spec.md missing the `## Co-change checklist` template header"
    )


def test_co_change_checklist_placeholder_format(step_6_region: str) -> None:
    """REQ-009-05 AC: the per-site placeholder format is documented verbatim."""
    placeholder = "- [ ] {file_path}:{line_or_section} -- {what changes}"
    assert placeholder in step_6_region, (
        f"Step 6 missing the canonical placeholder format `{placeholder}`"
    )


def test_co_change_checklist_documents_emit_conditions(step_6_region: str) -> None:
    """The template names BOTH emit conditions (opt-in flag AND auto-detect)."""
    # Proposer-flag (opt-in) condition.
    assert "multi-site contract change" in step_6_region.lower(), (
        "Step 6 must document the proposer-flag opt-in condition"
    )
    # Auto-detect condition (documented but not enforced at this milestone).
    assert "auto-detect" in step_6_region.lower() or "Auto-detect" in step_6_region, (
        "Step 6 must document the auto-detect rule (documentation-only)"
    )


def test_co_change_checklist_placement_documented(step_6_region: str) -> None:
    """The template specifies where the section sits in the generated REQ file.

    Per DESIGN-009: the section is inserted after the last
    `### Acceptance Criteria` subsection and before `### Rationale`.
    """
    assert "Acceptance Criteria" in step_6_region, (
        "Step 6 must reference Acceptance Criteria placement for the section"
    )
    assert "Rationale" in step_6_region, (
        "Step 6 must reference Rationale placement for the section"
    )


def test_co_change_checklist_concrete_example_present(step_6_region: str) -> None:
    """A concrete PR #1965 verdict-token example must be inline.

    Without an example, an LLM agent may emit the section in the wrong
    shape. The 17-site verdict-token cascade from PR #1965 is the
    canonical reference because it is documented end-to-end in the
    retrospective.
    """
    # The example demonstrates at least one verdict-token site.
    assert "verdict" in step_6_region.lower(), (
        "Step 6 must include a worked example referencing the verdict-token cascade"
    )
