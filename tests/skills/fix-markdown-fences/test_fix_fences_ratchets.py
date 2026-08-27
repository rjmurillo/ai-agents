#!/usr/bin/env python3
"""Ratchets and parity guards for the fix-markdown-fences scanner.

Split out of test_fix_fences_contracts.py when that file crossed the 500 line
taste ceiling. The seam is the question each class answers: the contracts file
asks whether the scanner agrees with `markdown-it-py`, and this one asks
whether the scanner's own pieces agree with each other and with their recorded
measurements. Parity between the two duplicated scripts, the curated case
inventory, the fuzz ratchets, and the detector-versus-repair pin all belong to
the second question.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_skills_import import import_skill_script
from commonmark_fence_cases import (
    CASE_COUNT,
    CASE_DIGEST,
    case_inventory,
    oracle_fence_lines,
)
from commonmark_fence_cases import CASES as FENCE_CASES
from commonmark_fence_fuzz import (
    FUZZ_BASELINE,
    FUZZ_DOCUMENTS,
    FUZZ_MIDDLE_REWRITES,
    random_documents,
)

# Same directory, but pytest's rootdir-based import does not put it on the
# path, so reach it the way the skill scripts are reached.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Imported as a MODULE, not by name. Importing `TestCommonMarkOracle` into this
# namespace makes pytest collect the whole class a second time, which inflates
# the suite by a few hundred duplicate cases and reports coverage that is not
# there. Reaching it through the module keeps one collection.
import test_fix_fences_contracts as contracts

_has_unclosed_fence = contracts._has_unclosed_fence
_inside_fence = contracts.TestCommonMarkOracle._inside_fence

mod = import_skill_script(".claude/skills/fix-markdown-fences/scripts/fix_fences.py")
find_fence_defects = mod.find_fence_defects
repair_markdown_fences = mod.repair_markdown_fences


class TestScannerParity:
    """The two scanners must not drift, and the fuzzer must see both.

    `_ListContainers` is duplicated byte-for-byte because the skills ship as
    separate plugin directories and neither is on the other's import path. The
    fuzz ratchet used to run only in the prose suite, so a regression in this
    scanner outside the curated cases would not have tripped it, and nothing
    compared the two copies.
    """

    def test_the_container_class_is_identical_in_both_scanners(self) -> None:
        prose = import_skill_script(".claude/skills/prose-self-check/scripts/prose_lint.py")
        assert inspect.getsource(mod._ListContainers) == inspect.getsource(prose._ListContainers), (
            "the duplicated container class has drifted between the two skills"
        )

    def test_the_link_grammar_is_identical_in_both_scanners(self) -> None:
        """The class is not the whole duplication, and the gap has cost five defects.

        Every defect found in this PR since round 12 landed in code sitting
        just OUTSIDE `_ListContainers`, where the parity test above could not
        see it: the line splitter, the closing-fence predicate, the test
        mirror, the oracle's own splitter, and the defect report's `rstrip`.
        Rule 16's grammar is the newest such code, and the destination scanner
        made it larger, so it is pinned here rather than left to the next
        reviewer.

        The patterns are compared by their source strings and the helpers by
        their source text, which is what a copy-paste divergence changes.
        """
        prose = import_skill_script(".claude/skills/prose-self-check/scripts/prose_lint.py")
        for name in ("_LINK_TITLE", "_LINK_LABEL"):
            assert getattr(mod, name) == getattr(prose, name), f"{name} has drifted"
        for name in ("_LINK_TITLE_ONLY", "_LINK_LABEL_ONLY", "_LINK_LABEL_COLON"):
            assert getattr(mod, name).pattern == getattr(prose, name).pattern, (
                f"{name} has drifted"
            )
        assert mod._TITLE_CLOSERS == prose._TITLE_CLOSERS, "_TITLE_CLOSERS has drifted"
        for name in (
            "_angle_destination_end",
            "_link_destination_end",
            "_link_tail",
            "_link_reference",
            "_title_end",
            "_label_opens",
            "_bare_title",
            "_Definition",
        ):
            assert inspect.getsource(getattr(mod, name)) == inspect.getsource(
                getattr(prose, name)
            ), f"{name} has drifted between the two skills"

    @pytest.mark.parametrize("seed", [1729, 4242, 20260826])
    def test_write_never_mutates_a_balanced_generated_document(self, seed: int) -> None:
        """Drive the PUBLIC repair path over the generated corpus.

        The seeded ratchet below compares `_inside_fence`, a hand-written
        mirror of the production loop. A mirror can drift from what it mirrors,
        and this one did, inside this PR: it omitted the malformed-closer
        re-scan and so agreed with the reference parser exactly where the
        shipped scanner does not. While it was wrong the baseline stayed green,
        because the baseline was measuring the mirror.

        This assertion cannot be fooled that way. It runs `find_fence_defects`
        and `repair_markdown_fences`, the two entry points the CLI uses, over
        every generated document, and demands that a document the reference
        parser reads as balanced comes back byte-identical. It is an absolute
        zero rather than a baseline: appending a fence to a well formed file is
        the corruption this whole module exists to prevent, so there is no
        acceptable non-zero count to ratchet down from.

        Documents carrying a mistaken closer are NOT excluded, because deciding
        that by asking `find_fence_defects` would let a regression that invents
        one exempt its own document from this assertion. The property asserted
        instead needs no such question and is strictly stronger: on a document
        the reference parser reads as balanced, the repair may rewrite the
        MIDDLE, which is what treating a mistaken closer looks like, and may
        never GROW AT THE END, which is what every corruption on this PR has
        looked like. Measured over the three seeds: 3,958 balanced documents,
        7 middle rewrites, 0 appends.
        """
        appended, rewritten = [], 0
        for text in random_documents(seed):
            if _has_unclosed_fence(text):
                continue
            repaired = repair_markdown_fences(text)
            if repaired == text:
                continue
            if repaired.startswith(text):
                appended.append(text)
            else:
                rewritten += 1
        # The zero-append assertion below is the corruption ratchet. This one
        # is its other half: a middle rewrite is the deliberate divergence, and
        # leaving it uncounted let a regression that invents new mistaken-closer
        # paths stay green as long as it never grew a document at the end.
        assert rewritten == FUZZ_MIDDLE_REWRITES[seed], (
            f"seed {seed}: {rewritten} middle rewrites against a pin of "
            f"{FUZZ_MIDDLE_REWRITES[seed]}. A middle rewrite is the tool acting "
            "on a mistaken closer, which is correct, so this is a declaration "
            "rather than a defect. Re-measure the pin if the change is intended."
        )
        mutated = appended
        assert mutated == [], (
            f"seed {seed}: --write mutated {len(mutated)} balanced document(s). "
            f"First: {mutated[0]!r}" if mutated else ""
        )

    @pytest.mark.parametrize("seed", sorted(FUZZ_BASELINE))
    def test_the_detector_and_the_repair_never_disagree(self, seed: int) -> None:
        """`find_fence_defects` and `repair_markdown_fences` are separate loops.

        They walk the same grammar twice, in two functions, over two hundred
        lines apart, and nothing held them together. Found while mutation
        checking the pin above: three mutations of the DETECTOR's closing
        branch moved no repair behaviour at all, because the repair has its own
        copy of that branch. A drift between them is a tool that reports a
        defect it will not fix, or fixes one it does not report, and either is
        worse than both being wrong the same way.

        Reporting a defect and acting on the document are the same question, so
        this asserts they answer it identically over every generated document.
        Measured at introduction: 0 disagreements across all three seeds and
        all 136 curated cases.
        """
        for text in random_documents(seed):
            reported = bool(find_fence_defects(text))
            acted = repair_markdown_fences(text) != text
            assert reported == acted, (
                f"seed {seed}: the detector says {reported} and the repair "
                f"says {acted} for {text!r}"
            )

    @pytest.mark.parametrize("name", sorted(FENCE_CASES))
    def test_the_detector_and_the_repair_agree_on_every_case(self, name: str) -> None:
        text = FENCE_CASES[name]
        assert bool(find_fence_defects(text)) == (repair_markdown_fences(text) != text), name

    def test_the_case_inventory_is_pinned(self) -> None:
        """The curated table must not be able to shrink silently.

        `CASES` decides both the fixtures AND how many parametrized tests this
        suite collects, so deleting a key deletes a contract instead of failing
        one and the suite still reports all green. That is the shape
        `FUZZ_BASELINE` carries, and it bites harder here: the generator emits
        no `[` in any of its 6,000 documents, so nothing else covers rule 16,
        which took five review rounds and eleven `--write` corruptions.

        Deliberately NOT parametrized, so it runs even when the dict is empty.
        The digest goes with the count because a count alone cannot see a
        delete-one-add-one edit.
        """
        count, digest = case_inventory()
        assert (count, digest) == (CASE_COUNT, CASE_DIGEST), (
            f"the curated case set changed: {count} cases, digest {digest}, "
            f"against a pin of {CASE_COUNT} and {CASE_DIGEST}. If the change is "
            "intended, re-measure the pin in commonmark_fence_cases.py rather "
            "than editing either value by hand."
        )

    def test_the_fuzz_seed_set_is_pinned(self) -> None:
        """The ratchet must not be able to disarm itself.

        `FUZZ_BASELINE` is both the expected value AND the seed list the test
        below is parametrized over, so deleting a key deletes the measurement
        rather than failing it. Measured: setting it to `{}` disarms BOTH fuzz
        ratchets and the suite still reports all green, and dropping to a single
        seed does the same for the other two.

        This test is deliberately NOT parametrized, so it runs even when the
        dict is empty. Same defect and same remedy as the corpus-size pin
        inside the test below: a ratchet whose own configuration decides
        whether it runs is not a ratchet.
        """
        assert sorted(FUZZ_BASELINE) == [1729, 4242, 20260826]

    @pytest.mark.parametrize("seed", sorted(FUZZ_BASELINE))
    def test_divergence_matches_baseline(self, seed: int) -> None:
        documents = random_documents(seed)
        # Pin the scope with an independent literal, on purpose. Comparing
        # only against FUZZ_DOCUMENTS is self-referential: `random_documents`
        # defaults `count` to it, so setting it to zero makes both sides zero
        # and turns the ratchet below into a no-op that still passes.
        assert len(documents) == 2000 == FUZZ_DOCUMENTS
        diverged = [
            text
            for text in documents
            if oracle_fence_lines(text) != _inside_fence(text)
        ]
        # Exact, for the reason given in the prose suite's twin: at-or-below
        # hides a fix and lets a later regression pass. One baseline serves
        # both scanners because the counts are equal, which is itself a check
        # that the duplicated class is behaving identically.
        assert len(diverged) == FUZZ_BASELINE[seed], (
            f"seed {seed}: {len(diverged)} diverged, baseline {FUZZ_BASELINE[seed]}. "
            + (f"First: {diverged[0]!r}" if diverged else "Lower the baseline.")
        )


class TestOpenLabelStateIsBounded:
    """An open label must cost the same whatever follows it.

    A link label may run across lines, so the scanner carries state from the
    `[` until the `]`. That state used to be the label text, rebuilt with
    `f"{self._open_label}\n{line}"` on every continuation line, so an
    unmatched `[` near the top of a file copied a growing buffer once per line
    below it. Measured on plain prose before the change, per-line cost rose
    with file size (7.5us at 2,000 lines, 13.3us at 8,000, 42.1us at 32,000)
    and doubling the file multiplied total time by 3 to 4 instead of by 2;
    32,000 lines took 1.35s. Afterwards the per-line cost is flat near 6.1us
    at every size, doubling costs 2.0x, and the same file takes 0.19s.

    Only `_finish_open_label` ever read that text, and only to ask whether the
    label was blank, so one bit replaced it.

    A wall-clock assertion would be the direct test and would also be flaky on
    a shared runner. This asserts the property underneath instead: whatever
    the scanner carries across a continuation line does not grow with the
    number of continuation lines. That rejects a return to the string and
    equally rejects accumulating a list of segments to join at closure, which
    is linear in time but still unbounded in space.
    """

    #: Enough continuation lines that any per-line accumulation is visible,
    #: cheap enough to run in the suite. The old string reached ~150KB here.
    LINES = 5000

    def _state_after(self, continuations: int) -> object:
        """Open a label, feed *continuations* plain lines, return the state."""
        containers = mod._ListContainers()
        containers.observe("[unclosed\n")
        for index in range(continuations):
            containers.observe(f"plain line {index} of ordinary prose\n")
        return containers._open_label_blank

    def test_the_state_does_not_grow_with_the_lines_it_spans(self) -> None:
        few, many = self._state_after(10), self._state_after(self.LINES)
        assert sys.getsizeof(few) == sys.getsizeof(many), (
            "the open-label state grew with the number of continuation lines, "
            "which is the quadratic accumulation this pin exists to reject"
        )

    def test_the_label_is_still_open_after_those_lines(self) -> None:
        """The pin above is vacuous if the label closed itself along the way.

        Without this, a regression that simply abandoned an open label on the
        next line would leave `None` at both sizes and pass the size check.
        """
        assert self._state_after(self.LINES) is not None

    def test_a_blank_label_and_a_filled_one_stay_distinguishable(self) -> None:
        """One bit is enough only if it still answers the question asked.

        `_finish_open_label` rejects a definition whose label normalises to
        empty, so the bit must be true for an all-whitespace run and false as
        soon as any line carries text.
        """
        blank = mod._ListContainers()
        blank.observe("[\n")
        blank.observe("   \n")
        blank.observe("\t\n")
        assert blank._open_label_blank is True

        filled = mod._ListContainers()
        filled.observe("[\n")
        filled.observe("   \n")
        filled.observe("  label text\n")
        filled.observe("   \n")
        assert filled._open_label_blank is False


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

    #: Measured, not assumed: every one of the 20 shapes is written to.
    CORRUPTING_SHAPES = 20

    def _shapes(self) -> list[str]:
        shapes = []
        for opener, closer in self.OPENERS:
            shapes.append(f"{opener}\n```\nAfter.\n")
            shapes.append(f"{opener}\n```\nAfter.\n{closer}\n")
        return shapes

    def test_the_shape_set_is_pinned(self) -> None:
        """Not parametrized, so it runs even if OPENERS is emptied.

        Same defect and remedy as the fuzz seed pin above: a ratchet whose own
        configuration decides whether it runs is not a ratchet.
        """
        assert len(self.OPENERS) == 10
        assert len(self._shapes()) == 20

    def test_the_corruption_count_has_not_grown(self) -> None:
        corrupting = [
            text
            for text in self._shapes()
            # The corruption class exactly: the ORACLE reads the input as
            # balanced, and the repair APPENDS. A middle rewrite is the
            # documented mistaken-closer divergence and does not count here.
            if not _has_unclosed_fence(text)
            and repair_markdown_fences(text).startswith(text)
            and repair_markdown_fences(text) != text
        ]
        assert len(corrupting) == self.CORRUPTING_SHAPES, (
            f"{len(corrupting)} of {len(self._shapes())} raw HTML shapes are written to, "
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
