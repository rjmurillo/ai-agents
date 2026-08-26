"""Contract tests for the prose-self-check scanner.

Contracts against things outside this module, split out from
test_prose_lint.py the way the fence suite splits its own.
`TestSiblingBoundCitation` replays the verbatim quote in prose_lint.py against
the sibling file it cites. `TestCommonMarkOracle` and `TestCommonMarkFuzz`
check the masking against `markdown-it-py`, a CommonMark reference
implementation and a declared dependency of this repository.

They answer to external contracts rather than to this scanner's own detector
behaviour, which is what makes them a separate file rather than a longer one.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script
from commonmark_fence_cases import CASES as FENCE_CASES
from commonmark_fence_cases import (
    oracle_fence_lines,
    reference_lines,
)
from commonmark_fence_fuzz import FUZZ_BASELINE, FUZZ_DOCUMENTS, random_documents

mod = import_skill_script(".claude/skills/prose-self-check/scripts/prose_lint.py")

PROJECT_ROOT = Path(__file__).resolve().parents[3]

CITATION = re.compile(r"^# `(?P<path>[^`]+)` lines (?P<first>\d+)-(?P<last>\d+), verbatim:$")


def _masked_lines(text: str) -> set[int]:
    """Return 0-indexed non-blank lines prose_lint blanks as fenced code."""
    masked, _ = mod._blank_fenced_blocks(text)
    # NOT `str.splitlines()`. `_blank_fenced_blocks` indexes its mask by real
    # line terminators, so pairing it with a splitlines list shifts every entry
    # after a U+0085 or U+2028 and compares two different lines.
    source = reference_lines(text)
    return {
        index
        for index, line in enumerate(source)
        if line != "" and index < len(masked) and masked[index] == ""
    }


def extract_citation(source_lines: list[str]) -> tuple[str, int, int, list[str]]:
    """Return (path, first, last, quoted lines) from a verbatim-citation comment.

    The comment shape is a citation line, a bare `#`, the quoted lines each
    prefixed with `# `, then a closing bare `#`.
    """
    for index, line in enumerate(source_lines):
        match = CITATION.match(line)
        if match is None:
            continue
        cursor = index + 1
        assert source_lines[cursor] == "#", "citation must be followed by a bare '#'"
        cursor += 1
        quoted: list[str] = []
        while source_lines[cursor] != "#":
            assert source_lines[cursor].startswith("# "), source_lines[cursor]
            quoted.append(source_lines[cursor][2:])
            cursor += 1
        return match["path"], int(match["first"]), int(match["last"]), quoted
    raise AssertionError("no verbatim citation found")


class TestSiblingBoundCitation:
    """The verbatim quote of the sibling scanner's bound stays replayable.

    `canonical-source-mirror.md` requires the claim to cite a path and quote the
    contract verbatim. A hand-written line range goes stale the moment either
    file moves, which it did once in review. This pins both.
    """

    SCRIPT = PROJECT_ROOT / ".claude" / "skills" / "prose-self-check" / "scripts" / "prose_lint.py"

    def _cited(self) -> tuple[str, int, int, list[str]]:
        return extract_citation(self.SCRIPT.read_text(encoding="utf-8").splitlines())

    def test_sibling_bound_quote_matches_its_source(self) -> None:
        rel, first, last, quoted = self._cited()
        target = PROJECT_ROOT / ".claude" / rel
        assert target.is_file(), f"cited path does not resolve: {target}"
        actual = target.read_text(encoding="utf-8").splitlines()[first - 1 : last]
        assert quoted == actual, (
            f"citation drifted from {rel}:{first}-{last}\nquoted: {quoted}\nactual: {actual}"
        )

    def test_cited_path_is_plugin_root_relative(self) -> None:
        # A `.claude/` prefix resolves to nothing in the src/copilot-cli mirror
        # this file ships into, so the citation must be relative to the root.
        rel, _, _, _ = self._cited()
        assert not rel.startswith((".claude/", "src/")), rel
        assert rel.startswith("skills/"), rel

    def test_quote_is_the_load_bearing_bound(self) -> None:
        _, _, _, quoted = self._cited()
        body = "\n".join(quoted)
        assert "def over_indented" in body
        assert "_MAX_FENCE_INDENT" in body

    def test_pin_fails_when_the_range_drifts(self) -> None:
        # Negative control: shift the cited range by one and the pin must break.
        rel, first, last, quoted = self._cited()
        shifted = (
            (PROJECT_ROOT / ".claude" / rel)
            .read_text(encoding="utf-8")
            .splitlines()[first : last + 1]
        )
        assert quoted != shifted, "the pin cannot detect drift on this input"


class TestCommonMarkOracle:
    """Masking matches `markdown-it-py` on every list-container case.

    Hand-written expectations are what let the first batch of CommonMark rules
    land wrong. These compare against a reference implementation instead. The
    count that used to sit in this sentence went stale as the rules grew.
    """

    @pytest.mark.parametrize("name", sorted(FENCE_CASES))
    def test_masked_lines_match_the_reference_parser(self, name: str) -> None:
        text = FENCE_CASES[name]
        assert _masked_lines(text) == oracle_fence_lines(text), name


class TestCommonMarkFuzz:
    """Randomized differential fuzzing against the reference parser.

    The curated cases each pin one rule; this answers what is left. That
    residue is described in `commonmark_fence_cases`, and this docstring used
    to restate it, which meant it went stale the moment rule 10 closed the
    family it named. It now points at the one description instead of keeping a
    second copy. Ratchet, not a pass/fail oracle: lower it, never raise it to
    make a run pass.
    """

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
        diverged = [text for text in documents if oracle_fence_lines(text) != _masked_lines(text)]
        # Equality, not at-or-below. `tests/ci/test_cli_exit_contract_ratchet.py`
        # states the rule for every counting ratchet in this repository:
        #
        #     a baseline above the real count is dead allowance, and a baseline
        #     below it means every pull request is red for a reason that has
        #     nothing to do with its diff
        #
        # At-or-below hides a fix that lowers the count, so a later regression
        # back up to the stale number passes. Lower the baseline when a rule
        # closes residue; that is the point of the ratchet.
        assert len(diverged) == FUZZ_BASELINE[seed], (
            f"seed {seed}: {len(diverged)} diverged, baseline {FUZZ_BASELINE[seed]}. "
            + (f"First: {diverged[0]!r}" if diverged else "Lower the baseline.")
        )

    def test_the_fuzzer_can_actually_see_a_divergence(self) -> None:
        # Negative control: a document from a known limitation must still
        # diverge, or the comparison above is measuring nothing. Raw HTML is
        # one of three the shared module lists, not the only one, and it is
        # hand-written here on purpose: the generator emits no `<` at all, so
        # this shape can never come out of the fuzz corpus.
        # This used to use a list-container case, which rule 10 then fixed, so
        # the control silently stopped controlling for anything.
        text = '<example type="X">\n```diff\n+ code\n```\nAfter.\n'
        assert oracle_fence_lines(text) != _masked_lines(text)
