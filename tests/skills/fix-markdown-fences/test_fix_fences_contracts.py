#!/usr/bin/env python3
"""Contract tests for the fix-markdown-fences scanner.

Contracts against things outside this module, listed rather than counted
because the count still said two after a third class landed.
`TestVendoredInvocation` executes the command SKILL.md documents, as shipped,
from a consumer working directory. `TestCommonMarkOracle` checks the
list-container model against `markdown-it-py`, a CommonMark reference
implementation. `TestScannerParity` holds the two duplicated scanners to one
behaviour and one source.

The detector and repair unit tests live in test_fix_fences.py; these are split
out because they answer to external contracts rather than to this module's own
behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

import inspect

from claude_skills_import import import_skill_script
from commonmark_fence_cases import CASES as FENCE_CASES
from commonmark_fence_cases import (
    oracle_fence_lines,
    reference_lines,
)
from commonmark_fence_fuzz import FUZZ_BASELINE, FUZZ_DOCUMENTS, random_documents
from markdown_it import MarkdownIt

PROJECT_ROOT = Path(__file__).resolve().parents[3]

mod = import_skill_script(".claude/skills/fix-markdown-fences/scripts/fix_fences.py")
repair_markdown_fences = mod.repair_markdown_fences
find_fence_defects = mod.find_fence_defects

_REFERENCE = MarkdownIt("commonmark")


def _has_unclosed_fence(text: str) -> bool:
    """Return True when the reference parser leaves a fence open at EOF.

    Read from the token rather than guessed from the string. A fence token
    spans its opener, its body, and its closing marker when one exists, while
    `content` holds the body alone, so a span exceeding opener plus body by a
    line was closed by a marker.

    No marker is not the same as open at EOF, and conflating them was the
    second bug in this helper. A fence can also end because its list item
    ended: `- ``` ` then a dedented line has no closing marker, and the
    reference parser still closes the token before the end. Calling that
    unclosed made the public no-op assertion skip the container-close
    behaviour it exists to guard. The first bug was cruder, asking whether the
    text ended in a fence character, which called two genuinely unclosed
    documents balanced.
    """
    # Reference numbering, not `str.splitlines()`: `token.map` is indexed the
    # way the parser counts lines, so a splitlines length can exceed it and
    # make an unclosed block look closed.
    source = reference_lines(text)
    for token in _REFERENCE.parse(text):
        if token.type != "fence" or not token.map:
            continue
        span = token.map[1] - token.map[0]
        body = token.content.count("\n")
        marked = span - 1 - body >= 1
        if not marked and token.map[1] >= len(source):
            return True
    return False


class TestCommonMarkOracle:
    """Fence tracking matches `markdown-it-py` on every list-container case.

    A repair tool that misplaces a list item's content column can append a
    closing fence into literal indented code, so the container model is checked
    against a reference implementation rather than against expectations.
    """

    @staticmethod
    def _inside_fence(text: str) -> set[int]:
        """Return 0-indexed non-blank lines the scanner treats as fenced.

        This mirrors the loop in `fix_fences.find_fence_defects`, including its
        container-close branch:

            if open_fence is not None and _container_closed(line.text, fence_base):
                open_fence = None  # the item holding the block ended

        its valid-close test, which is `_is_blank` and NOT `str.strip()`,
        because a closing fence may be followed only by spaces and tabs, and
        the malformed-closer transition that follows it:

            if _is_blank(match.group("info")):
                open_fence = None
                continue

            defects.append(...)
            open_fence = _scan_open(line.text, containers)
            fence_base = containers.base() if open_fence is not None else 0

        A hand-written mirror can drift from what it mirrors, which is the
        whole reason this comment names the branches. It drifted twice. It
        kept `str.strip()` for one commit after production moved to
        `_is_blank`. And it omitted the re-scan above entirely, so on a
        malformed closer it left the OLD opener active where production opens
        a new one. That second drift is the more dangerous shape, because it
        made this mirror AGREE with the reference parser on documents where
        production deliberately does not: the mirror was passing by not
        mirroring. See `test_a_malformed_closer_reopens_at_its_own_length`.

        `test_repair_is_a_no_op_on_balanced_documents` guards the direction
        that matters by driving the public repair path instead.
        """
        lines = mod._split_lines(text)
        containers = mod._ListContainers()
        open_fence = None
        fence_base = 0
        inside: set[int] = set()
        for index, line in enumerate(lines):
            if open_fence is not None and mod._container_closed(line.text, fence_base):
                open_fence = None  # the item holding the block ended
            if open_fence is None:
                open_fence = mod._scan_open(line.text, containers)
                fence_base = containers.base() if open_fence is not None else 0
                if open_fence is not None and line.text != "":
                    inside.add(index)
                continue
            if line.text != "":
                inside.add(index)
            match = mod._closes(line.text, open_fence, containers)
            if match is None:
                continue
            if mod._is_blank(match.group("info")):
                open_fence = None
                continue
            open_fence = mod._scan_open(line.text, containers)
            fence_base = containers.base() if open_fence is not None else 0
        return inside

    @pytest.mark.parametrize("name", sorted(FENCE_CASES))
    def test_fenced_lines_match_the_reference_parser(self, name: str) -> None:
        text = FENCE_CASES[name]
        assert self._inside_fence(text) == oracle_fence_lines(text), name

    @pytest.mark.parametrize("name", sorted(FENCE_CASES))
    def test_repair_is_idempotent_on_every_case(self, name: str) -> None:
        once = repair_markdown_fences(FENCE_CASES[name])
        assert repair_markdown_fences(once) == once, name

    @pytest.mark.parametrize("name", sorted(FENCE_CASES))
    def test_repair_is_a_no_op_on_balanced_documents(self, name: str) -> None:
        # Public path, no mirrored state machine. Where the reference parser
        # reads every fence as closed, `--write` must change nothing. This is
        # the assertion that would catch `_inside_fence` drifting from the
        # loops it mirrors, and it is how three separate corruption paths were
        # found: a fence on a marker line, a block outliving its list item, and
        # five-column padding before a marker-line fence.
        text = FENCE_CASES[name]
        if _has_unclosed_fence(text):
            pytest.skip("document is genuinely unclosed; repair should act")
        if any(d.kind == mod.MALFORMED_CLOSING for d in find_fence_defects(text)):
            # The shared module's Scope paragraph states this divergence: "a
            # fence carrying an info string inside an open block is content to
            # CommonMark but a mistaken closer to `fix_fences.py`, which is the
            # defect that tool exists to repair." Balanced therefore does not
            # imply no-op for this family, and asserting otherwise would demand
            # the tool stop doing its job. `test_a_mistaken_closer_is_repaired
            # _not_appended_to` pins what it does instead, so nothing here goes
            # unasserted.
            pytest.skip("document carries a mistaken closer; repair should act")
        assert repair_markdown_fences(text) == text, name

    def test_a_mistaken_closer_is_repaired_not_appended_to(self) -> None:
        """A closing fence may be followed only by spaces and tabs.

        `str.strip()` accepted U+00A0 there, so the block closed two lines
        early, the real closer read as a fresh opener, and `--write` appended a
        stray fence at EOF. That is the corruption class this suite exists to
        prevent, and no ratchet reached it: the corpus has no such document and
        the generator emitted no Unicode whitespace at all.

        The repair now inserts a bare closer above the mistaken one, which is
        the same treatment a ` ```python ` closer gets. Both assertions matter:
        the document must gain a closer in the right PLACE, and must not grow
        one at the end.
        """
        for text in (
            "```\nx\n```\u00a0\ny\n```\n",
            "```\nx\n```\u3000\ny\n```\n",
            "~~~\nx\n~~~\u00a0\ny\n~~~\n",
        ):
            marker = text.splitlines()[0]
            repaired = repair_markdown_fences(text)
            assert repaired.splitlines()[2] == marker, text
            assert not repaired.endswith(marker + "\n" + marker + "\n"), text
            assert repair_markdown_fences(repaired) == repaired, text

    def test_the_oracle_numbers_lines_the_way_the_reference_parser_does(self) -> None:
        """The ground truth must not disagree with itself depending on how it is asked.

        `markdown-it-py` normalizes CRLF and CR and then splits on newlines, so
        a token's `map` is indexed in that numbering. The oracle used to run its
        blank filter over `str.splitlines()`, which also breaks on U+000B,
        U+000C, U+001C to U+001E, U+0085, U+2028 and U+2029. Every entry after
        such a character shifts, so the filter read a different line than the
        token named.

        This matters more than a scanner bug: every measurement in this change
        is taken against this oracle. The two splitters give different answers
        on documents carrying those characters, which is what the second
        assertion pins.
        """
        text = "```\n\u0085\n\nz\n```\nafter\n"

        assert oracle_fence_lines(text) == {0, 1, 3, 4}

        # Teeth: recompute with the splitter the oracle used to use. If this
        # ever stops differing, the document no longer exercises the bug and
        # the assertion above has quietly stopped guarding anything.
        naive: set[int] = set()
        source = text.splitlines()
        for token in _REFERENCE.parse(text):
            if token.type == "fence" and token.map:
                start, stop = token.map
                naive.update(
                    i for i in range(start, min(stop, len(source))) if source[i] != ""
                )
        assert naive != oracle_fence_lines(text)

    def test_a_malformed_closer_reopens_at_its_own_length(self) -> None:
        """A mistaken closer becomes the next opener, at ITS fence length.

        This is the branch `_inside_fence` used to omit, and omitting it was
        not harmless: without the re-scan the mirror kept the ORIGINAL opener
        alive, so a later shorter bare fence appeared to close the block. That
        made the mirror agree with the reference parser on exactly the family
        where production deliberately disagrees, which is the worst way for a
        mirror to be wrong. It passes by not mirroring, and the fence suite's
        oracle assertion and fuzz baseline then describe a state machine the
        shipped scanner never runs.

        The `unclosed_block` text is the evidence: four fence characters, not
        the three the block opened with.
        """
        for text, reopened in (
            ("```\nx\n````py\ny\n```\nz\n", "````"),
            ("~~~\nx\n~~~~info\ny\n~~~\nz\n", "~~~~"),
        ):
            kinds = [(d.kind, d.text) for d in find_fence_defects(text)]
            assert (mod.MALFORMED_CLOSING, text.splitlines()[2]) in kinds, text
            assert (mod.UNCLOSED_BLOCK, reopened) in kinds, text
            repaired = repair_markdown_fences(text)
            assert repair_markdown_fences(repaired) == repaired, text

        # And the divergence is deliberate, so it is stated rather than left
        # for a future reader to discover by breaking it. The shared module's
        # Scope paragraph owns this boundary; these documents are the reason
        # they are NOT in the curated table, which asserts oracle agreement.
        divergent = "```\nx\n````py\ny\n```\nz\n"
        assert TestCommonMarkOracle._inside_fence(divergent) != oracle_fence_lines(divergent)

    def test_a_real_space_or_tab_still_closes_a_fence(self) -> None:
        """The inverse. Widening the predicate must not reject a valid closer."""
        for text in ("```\nx\n``` \n", "```\nx\n```\t\n"):
            assert find_fence_defects(text) == [], text
            assert repair_markdown_fences(text) == text, text

    def test_write_never_invents_a_fence_in_indented_code(self) -> None:
        # Rules 1 and 2: a marker that is itself indented code, or padding of
        # five or more columns, both used to move the content column and let
        # the repair append a closing fence into literal code.
        for name in ("marker over indented is code", "padding of five columns"):
            text = FENCE_CASES[name]
            assert oracle_fence_lines(text) == set(), name
            assert repair_markdown_fences(text) == text, name


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
        for name in ("_link_destination_end", "_link_tail", "_link_reference"):
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

        Documents carrying a mistaken closer are excluded for the reason the
        shared module's Scope paragraph gives: repairing those is the defect
        this tool exists to fix, so acting on them is correct.
        """
        mutated = [
            text
            for text in random_documents(seed)
            if not _has_unclosed_fence(text)
            and not any(d.kind == mod.MALFORMED_CLOSING for d in find_fence_defects(text))
            and repair_markdown_fences(text) != text
        ]
        assert mutated == [], (
            f"seed {seed}: --write mutated {len(mutated)} balanced document(s). "
            f"First: {mutated[0]!r}" if mutated else ""
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
            if oracle_fence_lines(text) != TestCommonMarkOracle._inside_fence(text)
        ]
        # Exact, for the reason given in the prose suite's twin: at-or-below
        # hides a fix and lets a later regression pass. One baseline serves
        # both scanners because the counts are equal, which is itself a check
        # that the duplicated class is behaving identically.
        assert len(diverged) == FUZZ_BASELINE[seed], (
            f"seed {seed}: {len(diverged)} diverged, baseline {FUZZ_BASELINE[seed]}. "
            + (f"First: {diverged[0]!r}" if diverged else "Lower the baseline.")
        )
