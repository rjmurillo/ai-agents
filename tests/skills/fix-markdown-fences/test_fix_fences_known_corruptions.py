#!/usr/bin/env python3
"""Pins for the gaps where `--write` is known to corrupt a balanced document.

Split out of test_fix_fences_ratchets.py when that file reached the 500 line
taste ceiling. The seam is the question each file answers: the ratchets file
asks whether the scanner's own pieces agree with each other and with their
recorded measurements, and this one asks what the scanner does to a document
it gets wrong.

Every class here holds a gap that was FILED AS A MISS and turned out to write.
There are four of them now (blockquote-interrupting-a-paragraph, raw HTML, a
setext underline under a list item, and an escaped tab in a single-line link
destination), and each was found the same way: by measuring the OUTPUT rather
than only the divergence. A gap is write-safe only when a test in this file
says so.

These are ratchets, not endorsements. Closing any part of a gap lowers its
counts and fails its test. Lower the pin; never raise it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_skills_import import import_skill_script
from commonmark_fence_cases import oracle_fence_lines

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Imported as a MODULE, not by name, so pytest does not collect the contracts
# suite a second time. Same reason as the ratchets file.
import test_fix_fences_contracts as contracts

_has_unclosed_fence = contracts._has_unclosed_fence

mod = import_skill_script(".claude/skills/fix-markdown-fences/scripts/fix_fences.py")
find_fence_defects = mod.find_fence_defects
repair_markdown_fences = mod.repair_markdown_fences


class TestRawHtmlIsADestructiveGap:
    """Pin the one known gap where `--write` corrupts, so it cannot spread.

    A raw HTML block swallows a following fence: CommonMark reads the whole
    run as HTML and sees no fence at all, so the document is balanced, while
    this scanner reads the fence and `--write` appends a closer to it. That is
    the corruption class, not a miss, and it is the worst gap on the list.

    Nothing measured it before. The existing negative control
    (`test_the_fuzzer_can_actually_see_a_divergence` in the prose suite) uses a
    raw HTML document but asserts only that the MASKING diverges; it says
    nothing about what `--write` then does. So the destructive half was
    documented in prose and pinned nowhere, which is how it stayed described as
    a disagreement while being a bad write.

    This is a ratchet in the repository's usual sense and NOT an endorsement.
    Closing any part of the gap lowers the count and fails this test, which is
    the point: re-measure and lower it, never raise it.
    """

    #: One opener per CommonMark HTML block type, each wrapping a fence, in
    #: both the terminated and unterminated form. Kept as data so the scope
    #: cannot be computed from the system under test.
    OPENERS = (
        ("<script>", "</script>"),
        ("<pre>", "</pre>"),
        ("<style>", "</style>"),
        ("<!-- c", "-->"),
        ("<?php", "?>"),
        ("<!DOCTYPE", ">"),
        ("<![CDATA[", "]]>"),
        ("<div>", "</div>"),
        ("<table>", "</table>"),
        ("<x-tag>", "</x-tag>"),
    )

    #: Shapes that do NOT corrupt today, carried so the count below is not
    #: pinned at its own maximum. An audit caught the first version of this
    #: class doing exactly that: `CORRUPTING_SHAPES` was 20 out of 20
    #: possible, so the "the gap spread" direction its failure message
    #: promises could never fire, and a mutation that multiplied `--write`
    #: corruption elsewhere left it green. A ratchet that can only move one
    #: way is half a ratchet.
    CLEAN_SHAPES = (
        # The fence closes inside the HTML block, so there is nothing to append.
        "<div>\n```\nAfter.\n```\n",
        "<!-- c\n```\nAfter.\n```\n-->\n",
        # Not an HTML block: a lone `<` and a bare word in angle brackets that
        # CommonMark does not treat as a block start.
        "< div>\n```\nAfter.\n```\n",
        "a <span>b</span>\n```\nAfter.\n```\n",
    )

    #: Measured, not assumed: every one of the 20 HTML shapes is written to,
    #: and none of the 4 clean shapes is.
    CORRUPTING_SHAPES = 20

    def _shapes(self) -> list[str]:
        shapes = []
        for opener, closer in self.OPENERS:
            shapes.append(f"{opener}\n```\nAfter.\n")
            shapes.append(f"{opener}\n```\nAfter.\n{closer}\n")
        return shapes

    def _all_shapes(self) -> list[str]:
        return self._shapes() + list(self.CLEAN_SHAPES)

    def test_the_shape_set_is_pinned(self) -> None:
        """Not parametrized, so it runs even if OPENERS is emptied.

        Same defect and remedy as the fuzz seed pin above: a ratchet whose own
        configuration decides whether it runs is not a ratchet.
        """
        assert len(self.OPENERS) == 10
        assert len(self._shapes()) == 20
        assert len(self.CLEAN_SHAPES) == 4
        # The headroom that lets the count rise. Without it the assertion below
        # compares a subset of a 20-element set against 20 and cannot fail
        # upward.
        assert len(self._all_shapes()) == 24 > self.CORRUPTING_SHAPES

    def test_the_corruption_count_has_not_grown(self) -> None:
        corrupting = [
            text
            for text in self._all_shapes()
            # The corruption class exactly: the ORACLE reads the input as
            # balanced, and the repair APPENDS. A middle rewrite is the
            # documented mistaken-closer divergence and does not count here.
            if not _has_unclosed_fence(text)
            and repair_markdown_fences(text).startswith(text)
            and repair_markdown_fences(text) != text
        ]
        assert len(corrupting) == self.CORRUPTING_SHAPES, (
            f"{len(corrupting)} of {len(self._all_shapes())} shapes are written to, "
            f"pinned at {self.CORRUPTING_SHAPES}. If a fix lowered this, lower the pin. "
            "If something raised it, the gap spread and that is a regression."
        )

    def test_the_scanner_and_the_oracle_disagree_about_seeing_a_fence(self) -> None:
        """The reason for the write, asserted rather than assumed.

        Without this, a future change could leave the write count at 20 for a
        different reason and the pin above would not notice.
        """
        text = "<div>\n```\nAfter.\n"
        assert oracle_fence_lines(text) == set(), (
            "the reference parser is supposed to see NO fence here; if it now "
            "does, this whole class has changed and the pin needs re-deriving"
        )
        assert find_fence_defects(text), "the scanner is supposed to report a defect here"


class TestSetextUnderAListItemIsDestructive:
    """The third gap filed as a miss that turned out to corrupt.

    A setext `===` underline directly under a list item, followed by a lazy
    continuation and then an indented fence: the list item ending closes the
    fence for CommonMark, so the document is balanced, and `--write` appends a
    second fence at top level, which leaves it genuinely unclosed.

    It was recorded as write-safe on a seven-shape run reporting none
    rewritten. Re-measured over the nine shapes below, seven are rewritten and
    six go in balanced and come out unclosed. Whatever the earlier run
    sampled, the family is not write-safe.

    That is three for three: blockquote-interrupting-a-paragraph, raw HTML,
    and this. Each was filed as a miss, each turned out destructive once
    someone measured the OUTPUT rather than only the divergence. The lesson is
    the procedure, not the entry: a gap is write-safe only when a test says
    so, and only these ratchets say so.

    Not introduced here. Four of these shapes append identically on
    `origin/main`; only the nested one is new to this branch, and over one
    40,000 document corpus the branch removes 318 corruptions relative to
    main and adds none. Nothing in the tracked corpus reaches this family.

    Ratchet, not endorsement. Closing any part of it lowers the counts and
    fails this test. Lower them; never raise.
    """

    #: Held as data so the scope cannot be computed from the system under test.
    SHAPES = {
        "trailing dedent": "- item\n===\nlazy\n  ```\nout\n",
        "body then dedent": "- item\n===\nlazy\n  ```\n  body\nout\n",
        "dedent then prose": "- item\n===\nlazy\n  ```\nout\nmore\n",
        "ordered marker": "1. item\n===\nlazy\n   ```\nout\n",
        "single equals": "- item\n=\nlazy\n  ```\nout\n",
        "nested item": "- a\n  - item\n  ===\n  lazy\n    ```\n  out\n",
        "fence closed in item": "- item\n===\nlazy\n  ```\n  body\n  ```\nout\n",
        "no lazy line": "- item\n===\n  ```\nout\n",
        "no trailing dedent": "- item\n===\nlazy\n  ```\n",
    }

    #: Measured, not assumed.
    REWRITTEN = 7
    BALANCED_IN_UNCLOSED_OUT = 6

    def test_the_shape_set_is_pinned(self) -> None:
        """Not parametrized, so emptying SHAPES cannot disarm the counts."""
        assert len(self.SHAPES) == 9

    def test_the_write_behaviour_has_not_moved(self) -> None:
        rewritten = corrupting = 0
        for text in self.SHAPES.values():
            out = repair_markdown_fences(text)
            if out == text:
                continue
            rewritten += 1
            # The damage stated as a property of the OUTPUT, which is what the
            # earlier seven-shape run never looked at: balanced going in,
            # unclosed coming out.
            if not _has_unclosed_fence(text) and _has_unclosed_fence(out):
                corrupting += 1
        assert (rewritten, corrupting) == (self.REWRITTEN, self.BALANCED_IN_UNCLOSED_OUT), (
            f"{rewritten} of {len(self.SHAPES)} rewritten and {corrupting} turned from "
            f"balanced into unclosed, pinned at {self.REWRITTEN} and "
            f"{self.BALANCED_IN_UNCLOSED_OUT}. Lower the pins if a fix closed part of "
            "the gap; a rise means it spread."
        )

    def test_the_smallest_shape_is_exactly_the_documented_one(self) -> None:
        """Pin the example the shipped docs quote, so the two cannot drift."""
        text = "- item\n===\nlazy\n  ```\nout\n"
        assert repair_markdown_fences(text) == "- item\n===\nlazy\n  ```\nout\n  ```\n"
        assert not _has_unclosed_fence(text), "input must be balanced for this to be a corruption"


class TestEscapedTabInASingleLineDestinationIsDestructive:
    """The fourth, and the one whose damage depends on an unrelated length.

    A backslash in a link destination escapes whatever follows it here, where
    CommonMark escapes only ASCII punctuation. That divergence is deliberate:
    the spec-derived rule was measured and is far worse, taking the curated
    shapes from 62 of 64 agreeing to 34 and introducing 30 `--write`
    corruptions, because the reference parser accepts a backslash before a
    control character.

    The escaped-TAB half has a second cause, and unlike the rest of that
    entry it writes. `_relative` expands tabs to four-column stops before the
    grammar sees the line, so how many expanded spaces the permissive rule
    eats depends on the column the tab sits at, and therefore on the LABEL'S
    LENGTH. Nine of the eleven lengths below turn a balanced document into an
    unclosed one; the two that do not are exactly the two whose label lands on
    a tab stop.

    Two controls say what the cause is not. The same escape reached through
    the next-line destination path corrupts none of eleven, because that path
    measures from column zero. The escaped-SPACE sibling corrupts none of
    eleven, because a space is one column wherever it sits. So this is
    specifically a tab arriving at the grammar already expanded, not the
    permissive escape rule on its own.

    Fixing it means giving the definition grammar the unexpanded line, which
    is a change to how every rule in it measures a column. That is why it is
    pinned here rather than fixed under an armed auto-merge.
    """

    LABEL_LENGTHS = tuple(range(1, 12))

    #: Measured. The clean ones are lengths 4 and 8, the tab stops.
    CORRUPTING_LENGTHS = 9
    CLEAN_LENGTHS = (4, 8)

    @staticmethod
    def _corrupts(text: str) -> bool:
        out = repair_markdown_fences(text)
        if out == text or not out.startswith(text):
            return False
        return not _has_unclosed_fence(text) and _has_unclosed_fence(out)

    def test_the_length_sweep_is_pinned(self) -> None:
        """Not parametrized, so shrinking the sweep cannot disarm the count."""
        assert len(self.LABEL_LENGTHS) == 11

    def test_the_single_line_path_still_corrupts_at_the_same_rate(self) -> None:
        hits = [
            n
            for n in self.LABEL_LENGTHS
            if self._corrupts("[" + "f" * n + "]: /u\\\trl\n2. ```\n   code\n   ```\n")
        ]
        assert len(hits) == self.CORRUPTING_LENGTHS, (
            f"{len(hits)} of {len(self.LABEL_LENGTHS)} label lengths corrupt, pinned at "
            f"{self.CORRUPTING_LENGTHS}. Lower the pin if a fix closed part of it."
        )
        # The reason, asserted rather than assumed: the survivors are the tab
        # stops. Without this the count could hold for an unrelated cause.
        assert tuple(n for n in self.LABEL_LENGTHS if n not in hits) == self.CLEAN_LENGTHS

    def test_the_next_line_destination_path_is_clean(self) -> None:
        """Control: the same escape, measured from column zero, never writes."""
        hits = [
            n
            for n in self.LABEL_LENGTHS
            if self._corrupts("[" + "f" * n + "]:\n/u\\\trl\n2. ```\n   code\n   ```\n")
        ]
        assert hits == [], f"the next-line path corrupted at lengths {hits}"

    def test_the_escaped_space_sibling_is_clean(self) -> None:
        """Control: a space is one column wherever it sits, so it never writes."""
        hits = [
            n
            for n in self.LABEL_LENGTHS
            if self._corrupts("[" + "f" * n + "]: /u\\ rl\n2. ```\n   code\n   ```\n")
        ]
        assert hits == [], f"the escaped-space sibling corrupted at lengths {hits}"
