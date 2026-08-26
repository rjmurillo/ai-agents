"""Tests for the prose-self-check Layer 1 and Layer 2 detectors.

Covers what the scanner finds in text: the banned-word list parsed from the
voice rule, the high and low severity tiers, what counts as code and is
skipped, the structural shapes, and the tokenizer. The CLI contract lives in
test_prose_lint_cli.py.
"""

from __future__ import annotations

import io
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
    FUZZ_BASELINE,
    FUZZ_DOCUMENTS,
    oracle_fence_lines,
    random_documents,
    reference_lines,
)

mod = import_skill_script(".claude/skills/prose-self-check/scripts/prose_lint.py")
lint_prose = mod.lint_prose
parse_banned_words = mod.parse_banned_words
discover_rules_file = mod.discover_rules_file
main = mod.main
scan_prose = mod.scan_prose
HIGH = mod.HIGH
INFO = mod.INFO

PROJECT_ROOT = Path(__file__).resolve().parents[3]
VOICE_RULE = PROJECT_ROOT / ".claude" / "rules" / "voice.md"

BANNED = {"delve", "robust", "comprehensive", "nuanced", "significant", "landscape"}


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


def kinds(text: str, banned: set[str] | None = None) -> list[str]:
    return [f.kind for f in lint_prose(text, BANNED if banned is None else banned)]


class TestParseBannedWords:
    """The list is read from the rule, never embedded in the script."""

    def test_reads_the_real_voice_rule(self) -> None:
        words = parse_banned_words(VOICE_RULE.read_text(encoding="utf-8"))
        assert {"delve", "robust", "tapestry", "significant"} <= words

    def test_stops_at_the_next_heading(self) -> None:
        text = "## Banned Vocabulary\n\n`delve`, `robust`.\n\n## Next\n\n`keepme`\n"
        assert parse_banned_words(text) == {"delve", "robust"}

    def test_ignores_multi_word_and_path_tokens(self) -> None:
        text = "## Banned Vocabulary\n\n`delve`, `some phrase`, `scripts/x.py`, `--flag`.\n"
        assert parse_banned_words(text) == {"delve"}

    def test_missing_section_yields_empty_set(self) -> None:
        assert parse_banned_words("# Voice\n\nNo list here.\n") == set()

    def test_script_does_not_embed_the_word_list(self) -> None:
        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "tapestry" not in source
        assert "multifaceted" not in source


class TestLexicalLayer:
    """Layer 1: dashes and banned vocabulary."""

    def test_em_dash_is_high_severity(self) -> None:
        findings = lint_prose("A sentence — with a dash.\n", BANNED)
        assert [(f.kind, f.severity) for f in findings] == [("em_dash", HIGH)]

    def test_en_dash_is_high_severity(self) -> None:
        findings = lint_prose("Range 1 – 2.\n", BANNED)
        assert [(f.kind, f.severity) for f in findings] == [("en_dash", HIGH)]

    def test_hyphen_is_not_a_dash_finding(self) -> None:
        assert kinds("A well-known trade-off.\n") == []

    def test_banned_word_is_high_severity(self) -> None:
        findings = lint_prose("A robust design.\n", BANNED)
        assert [(f.kind, f.severity) for f in findings] == [("banned_word", HIGH)]

    def test_low_signal_word_is_info_only(self) -> None:
        findings = lint_prose("A comprehensive and nuanced plan.\n", BANNED)
        assert {f.severity for f in findings} == {INFO}
        assert {f.kind for f in findings} == {"banned_word_low_signal"}

    def test_match_is_case_insensitive_but_reports_original(self) -> None:
        findings = lint_prose("Robust things.\n", BANNED)
        assert findings[0].match == "Robust"

    def test_substring_of_a_longer_word_is_not_matched(self) -> None:
        assert kinds("The delveson build is fine.\n") == []

    def test_position_is_one_indexed(self) -> None:
        findings = lint_prose("ab robust\n", BANNED)
        assert (findings[0].line, findings[0].column) == (1, 4)


class TestCodeIsSkipped:
    """Prose rules do not apply to code."""

    def test_fenced_block_is_skipped(self) -> None:
        assert kinds("```python\n# robust — code\n```\n") == []

    def test_inline_code_span_is_skipped(self) -> None:
        assert kinds("The `robust` flag is set.\n") == []

    def test_tilde_fence_is_skipped(self) -> None:
        assert kinds("~~~\nrobust\n~~~\n") == []

    def test_prose_after_a_closed_fence_is_checked(self) -> None:
        assert kinds("```\nrobust\n```\n\nA robust claim.\n") == ["banned_word"]

    def test_marker_indented_four_spaces_is_not_a_fence(self) -> None:
        # CommonMark: four spaces past the containing block makes it an
        # indented code block, so the backticks are literal. Treating it as a
        # fence started masking and hid the prose after it.
        assert kinds("Text.\n\n    ```\n\nA robust design.\n") == ["banned_word"]

    def test_marker_indented_three_spaces_is_still_a_fence(self) -> None:
        assert kinds("Text.\n\n   ```\nA robust design.\n") == ["unterminated_fence"]

    def test_shorter_fence_does_not_close_a_longer_one(self) -> None:
        assert kinds("````\n```\nrobust\n```\n````\n") == []

    def test_utf8_bom_does_not_hide_a_first_line_fence(self, tmp_path: Path) -> None:
        # A surviving U+FEFF defeats the fence anchor and inverts open/close,
        # so identical content flipped from clean to four false findings.
        body = "```\nrobust significant landscape\n```\n\nOrdinary prose here.\n"
        with_bom = tmp_path / "bom.md"
        with_bom.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
        without = tmp_path / "plain.md"
        without.write_text(body, encoding="utf-8")
        assert main([str(without), "--rules", str(VOICE_RULE)]) == 0
        assert main([str(with_bom), "--rules", str(VOICE_RULE)]) == 0

    def test_bom_is_stripped_from_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # sys.stdin.read() does not honor utf-8-sig.
        monkeypatch.setattr("sys.stdin", io.StringIO("\ufeff```\nrobust\n```\n"))
        assert main(["-", "--rules", str(VOICE_RULE)]) == 0

    def test_stray_backticks_do_not_swallow_the_prose_between_them(self) -> None:
        # Two lone backticks paragraphs apart used to pair and blank
        # everything between, so a run missed real tells and exited 0.
        text = "Use a ` here.\n\nA robust design.\n\nAnd a ` there.\n"
        assert kinds(text) == ["banned_word"]

    def test_inline_span_wrapped_across_a_line_break_is_skipped(self) -> None:
        # A document that documents these tells wraps its examples.
        text = "Openers: `Honestly,` / `In today's\nlandscape`. Delete them.\n"
        assert kinds(text) == []

    def test_fence_marker_backticks_do_not_pair_with_an_inline_span(self) -> None:
        text = "```\ncode\n```\n\nA robust claim.\n"
        assert kinds(text) == ["banned_word"]


class TestStructuralLayer:
    """Layer 2: the sentence shapes readers actually cite."""

    @pytest.mark.parametrize(
        "text",
        [
            "This is not a bug, it's a feature.\n",
            "It is not just slow, it is wrong.\n",
            "Refactoring isn't about speed, it's about risk.\n",
            "The fix is not cosmetic, but rather structural.\n",
        ],
    )
    def test_contrast_framing_is_flagged(self, text: str) -> None:
        assert "contrast_framing" in kinds(text)

    def test_plain_negation_is_not_contrast_framing(self) -> None:
        assert kinds("This is not a bug. The loader drops the message.\n") == []

    @pytest.mark.parametrize(
        "text",
        [
            "Want me to also add a dashboard?\n",
            "I could also wire up the gate.\n",
            "Let me know if you'd like a follow-up.\n",
            "Would you like me to open an issue?\n",
        ],
    )
    def test_trailing_offer_is_flagged(self, text: str) -> None:
        assert kinds(text) == ["trailing_offer"]

    @pytest.mark.parametrize(
        "text",
        [
            "Honestly, the queue drains.\n",
            "Look, the loader is wrong.\n",
            "It's worth noting that the gate is red.\n",
            "In today's landscape, retries matter.\n",
        ],
    )
    def test_signposting_opener_is_flagged(self, text: str) -> None:
        assert "signposting" in kinds(text)

    def test_signposting_mid_sentence_is_not_flagged(self) -> None:
        # Capitalized so the line-start anchor is the only thing that can
        # reject it; the lowercase form passes even with the anchor deleted.
        assert kinds("We should Look, then decide.\n") == []

    @pytest.mark.parametrize(
        "text",
        [
            "This is not a bug,\nit's a feature.\n",
            "Refactoring isn't about speed,\nit's about risk.\n",
        ],
    )
    def test_tell_that_straddles_a_hard_wrap_is_caught(self, text: str) -> None:
        assert "contrast_framing" in kinds(text)

    def test_match_does_not_cross_a_paragraph_break(self) -> None:
        assert kinds("A thing is not here,\n\nit's elsewhere.\n") == []

    @pytest.mark.parametrize(
        "text",
        [
            "The failure is not a flake, it's a real bug.\n",
            "The queue is not slow, it's unbounded.\n",
        ],
    )
    def test_noun_phrase_subject_is_caught(self, text: str) -> None:
        # Anchoring on it/this/that missed every sentence with a real subject.
        assert "contrast_framing" in kinds(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Claim is inaccurate (7 lines, not 5), but immaterial.\n",
            "| `v` | Not recognized | Keep it, but Claude ignores |\n",
        ],
    )
    def test_ordinary_not_but_is_not_contrast_framing(self, text: str) -> None:
        assert kinds(text) == []

    def test_but_rather_is_still_contrast_framing(self) -> None:
        assert kinds("It is not cosmetic, but rather structural.\n") == ["contrast_framing"]

    def test_model_identity_phrase_is_flagged(self) -> None:
        assert kinds("As an AI language model, I cannot.\n") == ["model_identity"]

    def test_signposting_on_a_later_line_reports_that_line(self) -> None:
        # The pattern consumes the preceding newline, so the reported offset
        # must be advanced past it or every hit lands one line early.
        findings = lint_prose("Intro line.\nHonestly, the queue drains.\n", BANNED)
        assert [(f.line, f.column, f.kind) for f in findings] == [(2, 1, "signposting")]

    def test_findings_are_sorted_by_position(self) -> None:
        text = "Honestly, a robust plan.\nThis is not a bug, it's a feature.\n"
        findings = lint_prose(text, BANNED)
        assert [(f.line, f.column) for f in findings] == sorted(
            (f.line, f.column) for f in findings
        )


class TestTokenizer:
    """A banned word keeps its identity through possessives and compounds."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("the landscape's shape", "landscape's"),
            ("a landscape-level view", "landscape-level"),
            ("a robust design", "robust"),
        ],
    )
    def test_banned_word_forms_are_matched(self, text: str, expected: str) -> None:
        assert [f.match for f in lint_prose(text, BANNED)] == [expected]

    @pytest.mark.parametrize(
        "text",
        [
            "see https://x.com/robust for more",
            "    </existing_landscape>",
            "the field is called robust_mode",
        ],
    )
    def test_non_prose_context_is_skipped(self, text: str) -> None:
        assert lint_prose(text, BANNED) == []

    def test_low_signal_compound_stays_info(self) -> None:
        assert [f.severity for f in lint_prose("a comprehensive-ish plan", BANNED)] == [INFO]


class TestListNestedFences:
    """A fence marker's indent is measured from its list item, not column zero.

    The positive cases use tilde fences on purpose. When a backtick fence goes
    unrecognized its own marker backticks stay in the text, and the inline-code
    masker then pairs the opener's third backtick with the closer's first and
    blanks the body anyway. That accident hides the defect from the public API
    for backtick fences, so a backtick-based assertion here would pass against
    the broken measurement and prove nothing. A tilde fence carries no
    backticks, so its body is genuinely exposed.
    """

    def test_four_spaces_deep_inside_a_nested_item_is_a_fence(self) -> None:
        text = "- item\n  - nested:\n\n    ~~~\n    robust significant\n    ~~~\n\nDone.\n"
        assert kinds(text) == []

    def test_a_blank_line_does_not_close_the_containing_item(self) -> None:
        assert kinds("- item\n\n    ~~~\n    robust\n    ~~~\n\nDone.\n") == []

    def test_an_ordered_marker_opens_a_container(self) -> None:
        assert kinds("1. step\n\n      ~~~\n      robust\n      ~~~\n\nDone.\n") == []

    def test_top_level_four_space_marker_is_still_indented_code(self) -> None:
        assert kinds("Text.\n\n    ~~~\n\nA robust design.\n") == ["banned_word"]

    def test_four_spaces_past_the_container_is_indented_code(self) -> None:
        # The item's content column is 2, so a marker at 6 is four past it.
        assert kinds("- item\n\n      ~~~\n\nA robust design.\n") == ["banned_word"]

    def test_a_dedent_closes_the_container(self) -> None:
        text = "- item\n\nBack at top level.\n\n    ~~~\n\nA robust design.\n"
        assert kinds(text) == ["banned_word"]

    def test_repository_example_masks_its_list_nested_block(self) -> None:
        # docs/codeql-rollout-checklist.md carries a four-space-indented fence
        # under a nested list item. This asserts the masking directly because
        # the block is backtick-fenced, and the accident described in the class
        # docstring makes the public path blind to the difference here.
        example = PROJECT_ROOT / "docs" / "codeql-rollout-checklist.md"
        source = example.read_text(encoding="utf-8")
        opener = next(
            (
                index
                for index, line in enumerate(source.splitlines())
                if line.startswith("    ```") and not line.startswith("     ")
            ),
            None,
        )
        assert opener is not None, f"no four-space-indented fence in {example}"
        masked, unterminated = mod._blank_fenced_blocks(source)
        assert unterminated is None
        assert masked[opener : opener + 3] == ["", "", ""]


CITATION = re.compile(r"^# `(?P<path>[^`]+)` lines (?P<first>\d+)-(?P<last>\d+), verbatim:$")


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
