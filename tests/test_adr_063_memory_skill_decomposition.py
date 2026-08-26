#!/usr/bin/env python3
"""Structural tests for ADR-063 (memory skill decomposition).

ADR-063 is an accepted decision (maintainer acceptance 2026-06-17, per its own
`## Status` section) authored for issue #1947; it was DRAFT (Proposed) at
authoring time, before that acceptance (Copilot, PR #5209 round-11 review:
this line still called it DRAFT, contradicting the `status: accepted`
contract this file's own assertion below requires). These tests pin the
structural contract the adr-review gate and the project ADR convention
depend on:

- The file exists at the canonical path.
- It carries the canonical section headings (Status, Date, Context, Decision,
  Prior Art Investigation, Rationale with an Alternatives Considered table,
  Reversibility and Kill Criteria, Consequences, References).
- Its status resolves to "accepted" by calling the canonical adr-review
  detector, not by replicating it.
- It cross-references the boundary ADRs the issue requires (ADR-007, ADR-056)
  and the gate ADR (ADR-070, renumbered from the former ADR-062 collision per
  #2228).
- It contains no em-dash (U+2014) or en-dash (U+2013) per universal.md.

The status assertion CALLS `_get_adr_status` from
`.claude/skills/adr-review/scripts/detect_adr_changes.py` rather than
reimplementing it. An earlier revision replicated the parser's whole-file regex
`^status:\\s*(.+)$` and documented it as the canonical contract. That regex was
the defect issue #5189 fixed, so once the parser was corrected this file
asserted the opposite of the thing it claimed to mirror, and still passed,
because it never consulted the parser. Its docstring said the status resolved to
"proposed" while its assertion required "accepted" and the real parser returned
"unknown": three answers in one file.

ADR-063 had no frontmatter. The bare `status: accepted` line it carried in the
body of its Status section existed only because the broken parser searched the
whole document. Fixing the parser silently made this record undeclared, which
these tests could not see. The record now carries real frontmatter transcribing
the maintainer acceptance already recorded in its prose, and the orphan body
line is gone. Calling the parser is what keeps the two from diverging again
(`.claude/rules/canonical-source-mirror.md`).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADR_PATH = PROJECT_ROOT / ".agents" / "architecture" / "ADR-063-memory-skill-decomposition.md"

TESTS_SKILLS_DIR = str(PROJECT_ROOT / "tests" / "skills")
_paths_added: list[str] = []
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)
    _paths_added.append(TESTS_SKILLS_DIR)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
    _paths_added.append(str(PROJECT_ROOT))
try:
    from claude_skills_import import import_skill_script

    _detector = import_skill_script(
        ".claude/skills/adr-review/scripts/detect_adr_changes.py"
    )
    _index = import_skill_script("build/scripts/generate_adr_index.py")
finally:
    for p in _paths_added:
        sys.path.remove(p)
# U+2014 em-dash, U+2013 en-dash. Banned by .claude/rules/universal.md.
_DASH_PATTERN = re.compile("[\\u2013\\u2014]")


@pytest.fixture(scope="module")
def adr_text() -> str:
    assert ADR_PATH.is_file(), f"ADR file not found at canonical path: {ADR_PATH}"
    return ADR_PATH.read_text(encoding="utf-8")


def _resolve_status() -> str:
    """Ask the canonical detector. Never reimplement it here.

    Canonical source: `.claude/skills/adr-review/scripts/detect_adr_changes.py`,
    `_get_adr_status` at lines 246 to 315. Its contract, quoted verbatim from
    that docstring (lines 266 to 272):

        Returns :data:`STATUS_UNKNOWN` when the record declares no status: file
        missing or unreadable, no complete frontmatter block, malformed or
        non-mapping frontmatter, no ``status`` key, or a non-scalar value (a
        YAML sequence or mapping, [...]). ``unknown`` is a distinct sentinel;
        callers MUST NOT treat it as ``proposed``.

    and its terminal branch verbatim (lines 312 to 315):

        status = fields.get("status")
        if status is None or isinstance(status, (list, dict)):
            return STATUS_UNKNOWN
        return str(status).strip().lower()

    Two consequences bind the assertions below. The parser reads ONLY the
    leading fenced frontmatter block, so a bare ``status:`` line in the prose
    body resolves to ``unknown``, not ``proposed``. And the returned value is
    lowercased, so the frontmatter ``accepted`` this record declares is what
    `test_detector_resolves_status_to_accepted` compares against.

    Stricter/looser/different than canonical: none. This helper adds no
    parsing, no default, and no normalization of its own; it forwards one path
    and returns what the canonical parser returns.
    """
    return _detector._get_adr_status(ADR_PATH)


class TestExistenceAndTitle:
    def test_adr_file_exists_at_canonical_path(self) -> None:
        assert ADR_PATH.is_file()

    def test_title_names_the_decomposition_decision(self) -> None:
        """The canonical title extractor resolves this record's title correctly.

        This asserted `splitlines()[0]` until frontmatter was added, at which
        point the first line became `---` and the test failed for a reason
        unrelated to the title (ADR-073 lifecycle frontmatter now precedes
        it, issue #5190 backfill). Anchoring an assertion to a position
        rather than to the structure it means is the same coupling that let
        a body `status:` line pass as frontmatter for months.

        A later revision replaced the position anchor with
        ``[ln for ln in ... if ln.startswith("# ADR-063:")]``, which filters
        for the wanted line rather than locating the document's real first
        H1. A file beginning with a wrong H1 (``# Wrong title``) followed
        later by ``# ADR-063: ...`` still passed: the filter finds exactly
        one matching line regardless of where it sits. Copilot's review on
        PR #5230 caught this (2026-08-25); fixed by locating the first H1
        by position with a regex matching the canonical title extractor's.

        That fix still reimplemented the regex rather than calling the
        canonical function, and applied it to the whole file including
        frontmatter. The canonical extractor never sees frontmatter:
        `build_record` (`generate_adr_index.py:556,574`) calls
        `parse_frontmatter` first and passes only the returned body to
        `_extract_title`. A frontmatter YAML comment starting with `#`
        (ADR-068 and ADR-085 both open their block that way, per
        `parse_frontmatter`'s own docstring at lines 267-270) would match
        the reimplemented regex before the real title and could reject a
        document the canonical extractor accepts. A second Copilot pass
        caught this (2026-08-25).

        Fixed by calling the canonical functions directly instead of
        reimplementing them a second time: `_index.parse_frontmatter` then
        `_index._extract_title`. This closes the input-contract gap by
        construction, not by another hand-written regex that could drift
        again, and it still catches the original defect: verified by
        mutating the fixture body to open with a wrong H1, which shifts
        `_extract_title`'s return from "Decompose the Memory Skill Into
        Focused Sub-Skills" to "Wrong title" and fails this test's
        assertions below. A control confirmed a `# migration note`
        frontmatter comment does not affect the extracted title, the case
        this round's fix closes.

        That fix still did not match `build_record`'s own call shape: it
        passed `parse_frontmatter`'s raw `body` straight to `_extract_title`,
        but `build_record` (`generate_adr_index.py:563,574`) calls
        `_strip_fences(body)` first and passes the result, `prose`, to
        `_extract_title`. `_extract_title`'s own docstring
        (`generate_adr_index.py:356-360`) states the precondition directly:
        "Takes the fence-stripped body: a `# Heading` shown inside a
        markdown code sample is sample text, and one appearing above the
        record's own H1 used to be published as the record's title." Passing
        raw `body` means this test could accept a record `build_record`
        rejects (a fenced sample whose own `# Heading` sits above the real
        title) whenever the sample's H1 does not happen to also satisfy this
        test's loose substring assertions. A third Copilot pass caught this
        (2026-08-25). Fixed by inserting the missing `_strip_fences` call,
        matching `build_record`'s call shape exactly this time; proven by
        `test_extract_title_requires_fence_stripped_input_like_build_record_does`
        below, which fails on the raw-`body` call and passes once
        fence-stripping is inserted (verified by reverting the fix locally
        and re-running: the new test fails, the fenced-H1 wins).

        That fix, calling `parse_frontmatter`, `_strip_fences`, and
        `_extract_title` individually in the test body, still reimplemented
        `build_record`'s own call SEQUENCE rather than driving it: a future
        change to `build_record` that removes, reorders, or adds a step
        between those three calls would leave this test green, since it
        never runs `build_record` itself. Copilot found this on PR #5230
        round 16 (previously missed, then resurfaced). Fixed by calling
        `_index.build_record(ADR_PATH)` directly and asserting on the
        `AdrRecord.title` it returns: this test now exercises the exact
        production entry point every real ADR record goes through, and a
        regression in `build_record`'s own pipeline order breaks this test
        the same way it would break the real index build.
        `test_extract_title_requires_fence_stripped_input_like_build_record_does`
        below keeps its own direct calls to `parse_frontmatter`,
        `_strip_fences`, and `_extract_title`: it exists specifically to pin
        `_extract_title`'s fence-stripped-input precondition in isolation,
        on a synthetic fixture `build_record` cannot be pointed at, so it is
        not a duplicate of this test's coverage.
        """
        title = _index.build_record(ADR_PATH).title
        assert "memory" in title.lower()
        assert "decompos" in title.lower()

    def test_extract_title_requires_fence_stripped_input_like_build_record_does(
        self,
    ) -> None:
        """A fenced sample's own H1 must not outrank the record's real title.

        Synthetic fixture, not the real ADR-063 body: a fenced code sample
        containing `# Wrong title` sits before the record's real H1. This is
        exactly the shape `_extract_title`'s docstring names as the reason it
        requires fence-stripped input, and exactly what `build_record`
        (`generate_adr_index.py:563,574`) guards against by calling
        `_strip_fences(body)` before `_extract_title(prose, path)`.

        Negative control: calling `_extract_title` on the RAW body (skipping
        `_strip_fences`, the bug this test guards against) returns the
        fenced sample's title instead, proving the fixture discriminates.
        """
        raw_body = (
            "## Context\n\n"
            "```markdown\n"
            "# Wrong title\n"
            "```\n\n"
            "# ADR-063: Decompose the Memory Skill Into Focused Sub-Skills\n"
        )

        # Negative control: unstripped input is misled by the fenced H1.
        misled_title = _index._extract_title(raw_body, ADR_PATH)
        assert misled_title == "Wrong title"

        # The fix: strip fences first, matching build_record's call shape.
        prose = _index._strip_fences(raw_body)
        title = _index._extract_title(prose, ADR_PATH)
        assert title == "Decompose the Memory Skill Into Focused Sub-Skills"


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

    def test_detector_resolves_status_to_accepted(self) -> None:
        """The canonical detector reports accepted, asked rather than mimicked."""
        assert _resolve_status() == "accepted"

    def test_status_is_declared_in_frontmatter_not_the_body(
        self, adr_text: str
    ) -> None:
        """The declaration must sit in frontmatter, where ADR-073 puts it.

        This record previously declared status only as a bare line inside its
        prose Status section, which resolved solely because the parser searched
        the whole document. That is the defect issue #5189 closed, so a body
        declaration must not come back: it would read as machine-readable while
        being invisible to every corrected reader.
        """
        assert adr_text.startswith("---\n"), "frontmatter block missing"
        head, _, body = adr_text[4:].partition("\n---\n")
        assert re.search(r"(?m)^status:\s*accepted\s*$", head), head
        assert not re.search(r"(?m)^status:", body), (
            "a bare status: line survives in the body; it is invisible to the "
            "frontmatter-only parser and duplicates the frontmatter declaration"
        )


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
