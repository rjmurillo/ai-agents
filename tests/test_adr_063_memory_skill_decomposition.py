#!/usr/bin/env python3
"""Structural tests for ADR-063 (memory skill decomposition).

ADR-063 is a DRAFT (Proposed) decision authored for issue #1947. These tests
pin the structural contract the adr-review gate and the project ADR convention
depend on:

- The file exists at the canonical path.
- It carries the canonical section headings (Status, Date, Context, Decision,
  Prior Art Investigation, Rationale with an Alternatives Considered table,
  Reversibility and Kill Criteria, Consequences, References).
- Its status resolves to "proposed" via the adr-review detector contract
  (`status: proposed`), so the BLOCKING adr-review debate gate fires.
- It cross-references the boundary ADRs the issue requires (ADR-007, ADR-056)
  and the gate ADR (ADR-070, renumbered from the former ADR-062 collision per
  #2228).
- It contains no em-dash (U+2014) or en-dash (U+2013) per universal.md.

The status-detection assertion mirrors the canonical detector contract at
`.claude/skills/adr-review/scripts/detect_adr_changes.py:_get_adr_status`,
which extracts status with the regex `^status:\\s*(.+)$` and returns "proposed"
when no such line exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = PROJECT_ROOT / ".agents" / "architecture" / "ADR-063-memory-skill-decomposition.md"

# Mirrors detect_adr_changes.py:_get_adr_status (the adr-review detector).
_STATUS_FRONTMATTER = re.compile(r"(?m)^status:\s*(.+)$")
# U+2014 em-dash, U+2013 en-dash. Banned by .claude/rules/universal.md.
_DASH_PATTERN = re.compile("[\\u2013\\u2014]")


@pytest.fixture(scope="module")
def adr_text() -> str:
    assert ADR_PATH.is_file(), f"ADR file not found at canonical path: {ADR_PATH}"
    return ADR_PATH.read_text(encoding="utf-8")


def _resolve_status(content: str) -> str:
    """Replicate the adr-review detector's status resolution."""
    match = _STATUS_FRONTMATTER.search(content)
    if match:
        return match.group(1).strip().lower()
    return "proposed"


class TestExistenceAndTitle:
    def test_adr_file_exists_at_canonical_path(self) -> None:
        assert ADR_PATH.is_file()

    def test_title_names_the_decomposition_decision(self, adr_text: str) -> None:
        first_line = adr_text.splitlines()[0]
        assert first_line.startswith("# ADR-063:")
        assert "memory" in first_line.lower()
        assert "decompos" in first_line.lower()


class TestRequiredSections:
    REQUIRED_HEADINGS = (
        "## Status",
        "## Date",
        "## Context",
        "## Decision",
        "## Prior Art Investigation",
        "## Rationale",
        "## Reversibility and Kill Criteria",
        "## Consequences",
        "## References",
    )

    @pytest.mark.parametrize("heading", REQUIRED_HEADINGS)
    def test_required_heading_present(self, adr_text: str, heading: str) -> None:
        assert heading in adr_text, f"missing canonical section: {heading}"

    def test_alternatives_considered_table_present(self, adr_text: str) -> None:
        # The decision space is finite; the ADR must enumerate alternatives in a
        # table so reviewers see the rejected shapes (split by tier, by store,
        # by frequency, passive-context, do-nothing).
        assert "### Alternatives Considered" in adr_text
        assert "| Alternative |" in adr_text

    def test_enumerates_the_four_decomposition_shapes(self, adr_text: str) -> None:
        lowered = adr_text.lower()
        # Issue #1947 lists four shapes the ADR must consider.
        assert "by tier" in lowered or "split by tier" in lowered
        assert "operation" in lowered
        assert "source-of-truth" in lowered or "ownership" in lowered
        assert "frequency" in lowered


class TestAcceptedStatus:
    # ADR-063 was accepted by the maintainer on 2026-06-17 (commit f21c8d4ad7,
    # "docs(adr): accept ADR-063 memory-skill decomposition"). These assertions
    # previously pinned the pre-acceptance "Proposed" state so the BLOCKING
    # adr-review debate gate would fire. The maintainer-authorized acceptance is
    # now recorded in the ADR Status section and the `status: accepted`
    # frontmatter, so the gate is satisfied and the accepted state is the
    # contract these tests pin.
    def test_status_section_says_accepted(self, adr_text: str) -> None:
        # The literal Status section must read Accepted after maintainer sign-off.
        parts = adr_text.split("## Status", 1)
        assert len(parts) > 1, "Missing '## Status' section"
        status_block = parts[1].split("##", 1)[0]
        assert "Accepted" in status_block
        assert "Proposed" not in status_block

    def test_detector_resolves_status_to_accepted(self, adr_text: str) -> None:
        # The adr-review detector contract: the `status: accepted` frontmatter
        # line resolves to "accepted", satisfying the debate gate.
        assert _resolve_status(adr_text) == "accepted"

    def test_machine_readable_status_line_is_accepted(self, adr_text: str) -> None:
        # The machine-readable status line records the maintainer acceptance.
        match = _STATUS_FRONTMATTER.search(adr_text)
        assert match is not None, "Missing machine-readable status line"
        assert match.group(1).strip().lower() == "accepted"


class TestRequiredCrossReferences:
    @pytest.mark.parametrize("adr_ref", ["ADR-007", "ADR-056", "ADR-070"])
    def test_boundary_and_gate_adrs_cross_referenced(self, adr_text: str, adr_ref: str) -> None:
        # ADR-007 (memory-first) and ADR-056 (output envelope) are the boundary
        # constraints the issue requires; ADR-070 is the gate semantics to keep
        # (renumbered from the former ADR-062 collision per #2228).
        assert adr_ref in adr_text, f"missing required cross-reference: {adr_ref}"

    def test_gate_semantics_reference_uses_full_adr_070_filename(self, adr_text: str) -> None:
        # Gate ADR renumbered 062 -> 070 per #2228 dedup.
        assert "ADR-070-memory-first-gate-spec-pipeline.md" in adr_text

    def test_links_to_implementation_issue_1948(self, adr_text: str) -> None:
        # The ADR records the decision; #1948 implements it. The boundary must
        # be explicit so a reader does not mistake the ADR for the change.
        assert "#1948" in adr_text

    def test_links_to_source_issue_1947(self, adr_text: str) -> None:
        assert "#1947" in adr_text


class TestNoDashes:
    def test_contains_no_em_or_en_dash(self, adr_text: str) -> None:
        # universal.md bans U+2014 and U+2013 in authored text.
        match = _DASH_PATTERN.search(adr_text)
        assert match is None, f"prohibited dash at offset {match.start()}" if match else ""


class TestScopeBoundary:
    def test_states_it_does_not_implement_the_decomposition(self, adr_text: str) -> None:
        # The work-item and the issue both scope implementation out (it is #1948).
        # Collapse whitespace so a markdown line wrap inside the phrase does not
        # hide the assertion ("does not\nimplement" reflows to "does not implement").
        collapsed = re.sub(r"\s+", " ", adr_text.lower())
        assert "does not implement" in collapsed

    def test_flags_stale_adr_051_reference_in_issue(self, adr_text: str) -> None:
        # The issue cites "ADR-051: response envelope schema"; ADR-051 is the
        # Synthesis Panel Frontmatter Standard. The ADR must flag this so the
        # next reader does not chase the wrong constraint.
        assert "ADR-051" in adr_text
        assert "ADR-056" in adr_text

    def test_review_findings_are_reflected_in_implementation_notes(self, adr_text: str) -> None:
        lowered = adr_text.lower()
        assert "3 to 5 sub-skills" in lowered
        assert "graceful degradation" in lowered
        assert "path traversal" in lowered
