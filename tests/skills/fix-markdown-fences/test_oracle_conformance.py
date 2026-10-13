#!/usr/bin/env python3
"""Measure the oracle: run the CommonMark specification suite against it.

Every correctness claim in `fix-markdown-fences` and `prose-self-check` is
settled by `markdown-it-py` through `commonmark_fence_cases`. Until issue #5353
nothing had checked the oracle itself. This file turns its accuracy from a
reputation into numbers that anyone can re-run:

    uv run pytest tests/skills/fix-markdown-fences/test_oracle_conformance.py

The fixture is the upstream CommonMark 0.31.2 `spec.json`
(https://spec.commonmark.org/0.31.2/spec.json, CC BY-SA 4.0) stored minified on
one line, because a 5,000 line data file breaks the 500 line taste ceiling.
Re-serializing the parsed fixture with `json.dumps(indent=2, ensure_ascii=False)`
reproduces the upstream bytes, and the test pins that SHA-256. Re-vendoring a
newer spec is a decision, so a changed file fails loudly.

Every count below is an EQUALITY, not a floor. A `markdown-it-py` upgrade that
fixes an example, or breaks one, moves the number and fails the test, which is
the point: the authority changed, so re-measure the pinned counts downstream.

This file measures `markdown-it-py` against the specification. It does not
add a second parser. Option 2 of #5353 (a second implementation) was measured
once, outside this suite, and the result is in the appended section of
`.project-toolkit/retrospective/2026-08-27-pr5322-measure-the-fix-not-only-the-defect.md`.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from markdown_it import MarkdownIt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_skills_import import import_skill_script
from commonmark_fence_cases import oracle_fence_lines, reference_lines

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Imported as a MODULE so pytest does not collect the contracts suite twice.
import test_fix_fences_contracts as contracts

_has_unclosed_fence = contracts._has_unclosed_fence

mod = import_skill_script(".claude/skills/fix-markdown-fences/scripts/fix_fences.py")
repair_markdown_fences = mod.repair_markdown_fences

SPEC_PATH = Path(__file__).resolve().parent / "fixtures" / "commonmark-spec-0.31.2.json"
UPSTREAM_SPEC_SHA256 = "d431b29d97b6f73e69d547109cf5081578fac931e72afe95639ebe766c1b2a20"
SPEC_EXAMPLES = 652

# Re-measure with:
#   uv run pytest tests/skills/fix-markdown-fences/test_oracle_conformance.py -k pass_count
HTML_EXACT = 649
# All three are an empty block quote: the spec writes `<blockquote>\n</blockquote>`
# and the oracle writes `<blockquote></blockquote>`. The spec's own test harness
# normalizes whitespace between tags, so this is a rendering style difference.
HTML_MISSES = frozenset({218, 239, 240})

FENCED_SECTION = "Fenced code blocks"
FENCED_EXAMPLES = 29
# Example 134 is a four-space-indented run that LOOKS like a fence. It is
# indented code, so the helper must return no fence line for it.
INDENTED_LOOKALIKE = 134
# Examples whose expected HTML holds no <pre><code>: the helper must find no fence.
NO_CODE_EXAMPLES = 570

_MD = MarkdownIt("commonmark")
_PRE = re.compile(r"<pre[^>]*><code[^>]*>(.*?)</code></pre>", re.S)
_FENCE_MARKER = re.compile(r"^[ >]*(`{3,}|~{3,})")


Example = dict[str, Any]


def _load_spec() -> list[Example]:
    return cast("list[Example]", json.loads(SPEC_PATH.read_text(encoding="utf-8")))


SPEC = _load_spec()


def _expected_code_lines(spec_html: str) -> list[str]:
    """Non-empty lines of every code block in the spec's expected HTML."""
    lines: list[str] = []
    for body in _PRE.findall(spec_html):
        lines.extend(line for line in html.unescape(body).split("\n") if line != "")
    return lines


def helper_agrees_with_spec(example: Example, fence_lines: set[int] | None = None) -> bool:
    """Check the helper's fence lines against code the SPEC says is present.

    The expected code body comes from the spec's HTML, not from the parser, so
    this does not ask the oracle to grade itself. A fence is an opening marker,
    the body lines, and an optional closing marker, so the helper must return
    one or two more lines than the spec shows, framed by marker lines.
    """
    source = reference_lines(example["markdown"])
    found = sorted(oracle_fence_lines(example["markdown"]) if fence_lines is None else fence_lines)
    expected = _expected_code_lines(example["html"])
    if not found:
        return not expected
    framing = len(found) - len(expected)
    if framing not in (1, 2) or not _FENCE_MARKER.match(source[found[0]]):
        return False
    body = found[1 : 1 + len(expected)]
    if any(not source[index].endswith(line) for index, line in zip(body, expected, strict=False)):
        return False
    return framing == 1 or bool(_FENCE_MARKER.match(source[found[-1]]))


def _fenced_examples() -> list[Example]:
    return [e for e in SPEC if e["section"] == FENCED_SECTION]


class TestVendoredSpec:
    def test_the_fixture_reproduces_the_pinned_upstream_bytes(self) -> None:
        upstream = json.dumps(SPEC, indent=2, ensure_ascii=False).encode("utf-8")
        assert hashlib.sha256(upstream).hexdigest() == UPSTREAM_SPEC_SHA256
        assert len(SPEC) == SPEC_EXAMPLES

    def test_the_fenced_section_is_present_and_whole(self) -> None:
        # A fixture trimmed to pass would keep the digest only if the digest
        # were edited too; this catches the section silently emptying.
        assert len(_fenced_examples()) == FENCED_EXAMPLES


class TestHtmlConformance:
    def test_html_pass_count_is_pinned(self) -> None:
        misses = {e["example"] for e in SPEC if _MD.render(e["markdown"]) != e["html"]}
        assert SPEC_EXAMPLES - len(misses) == HTML_EXACT
        assert misses == HTML_MISSES

    @pytest.mark.parametrize("number", sorted(HTML_MISSES))
    def test_each_miss_is_an_empty_block_quote_spacing_difference(self, number: int) -> None:
        example = next(e for e in SPEC if e["example"] == number)
        empty_quote = "<blockquote>\n</blockquote>"
        spacing_normalized = example["html"].replace(empty_quote, "<blockquote></blockquote>")
        assert _MD.render(example["markdown"]) == spacing_normalized

    def test_every_fenced_code_example_renders_exactly(self) -> None:
        wrong = [e["example"] for e in _fenced_examples() if _MD.render(e["markdown"]) != e["html"]]
        assert wrong == []


class TestFenceHelperAgainstTheSpec:
    @pytest.mark.parametrize(
        "example",
        [e for e in _fenced_examples() if e["example"] != INDENTED_LOOKALIKE],
        ids=lambda e: f"example-{e['example']}",
    )
    def test_helper_lines_frame_the_code_the_spec_shows(self, example: Example) -> None:
        assert helper_agrees_with_spec(example)

    def test_an_indented_lookalike_is_not_a_fence(self) -> None:
        example = next(e for e in SPEC if e["example"] == INDENTED_LOOKALIKE)
        assert oracle_fence_lines(example["markdown"]) == set()
        assert _expected_code_lines(example["html"]) != []

    def test_no_example_without_code_yields_a_fence_line(self) -> None:
        plain = [e for e in SPEC if "<pre><code" not in e["html"]]
        assert len(plain) == NO_CODE_EXAMPLES
        assert [e["example"] for e in plain if oracle_fence_lines(e["markdown"])] == []

    def test_the_agreement_check_can_fail(self) -> None:
        """Negative control: a wrong line set must be rejected, or the pins above prove nothing."""
        example = next(e for e in SPEC if e["example"] == 142)
        real = oracle_fence_lines(example["markdown"])
        assert helper_agrees_with_spec(example, real)
        assert not helper_agrees_with_spec(example, real - {2})  # a body line gone
        assert not helper_agrees_with_spec(example, set())


# The six claims refuted with measurement on PR #5322 (issue #5353, row 8 of the
# owner table). Each document is the reviewer's shape; each is re-checked here
# against the oracle and the scanner. `unclosed` is whether the oracle sees an
# unclosed fence, which decides whether `--write` is SUPPOSED to change it. A
# claim stays refuted while a balanced document is untouched and an unclosed one
# is closed.
REFUTED_CLAIMS = {
    "label cap, 999 characters": ("[" + "a" * 999 + "]: /url\n2. ~~~\n   code\n", True),
    "label cap, 1000 characters": ("[" + "a" * 1000 + "]: /url\n2. ~~~\n   code\n", True),
    "raw less-than in a bare destination": ("[foo]: /a<b\n2. ~~~\n   code\n", True),
    "raw greater-than in a bare destination": ("[foo]: /a>b\n2. ~~~\n   code\n", True),
    "container pop": ('- [foo]: /url\n"title"\n2. ~~~\n   code\n', True),
    "stale pending destination": ("[foo]:\n    a b\n/url\n2. ```\ncode\n", False),
    "U+00A0 item then nested ordered marker": ("-  \n  2. ```\n  code\n", False),
}


class TestRefutedClaimsStayRefuted:
    @pytest.mark.parametrize("name", sorted(REFUTED_CLAIMS))
    def test_write_changes_a_document_only_when_the_oracle_says_unclosed(self, name: str) -> None:
        text, unclosed = REFUTED_CLAIMS[name]
        repaired = repair_markdown_fences(text)
        assert (not _has_unclosed_fence(text)) is (not unclosed)
        assert (repaired != text) is unclosed
        assert not _has_unclosed_fence(repaired)

    def test_a_claim_stays_refuted_only_when_both_directions_are_present(self) -> None:
        # Scope is data and both directions are asserted, so emptying one half
        # of the table cannot leave the other half passing alone.
        flags = {unclosed for _, unclosed in REFUTED_CLAIMS.values()}
        assert flags == {True, False}

    def test_the_empty_document_has_no_reference_lines(self) -> None:
        assert reference_lines("") == []


class TestKnownDivergenceFromTheReferenceImplementations:
    """`markdown-it-py` reads a definition then `2.` as a list; cmark-gfm does not.

    Measured once with cmarkgfm 2025.10.22 (GitHub's cmark-gfm) and commonmark.py 0.9.2:
    both render `[foo]: /url` / `2. bar` as a paragraph, because a link
    reference definition is parsed out of an OPEN paragraph and an ordered
    marker other than 1 cannot interrupt a paragraph. `markdown-it-py` consumes
    the definition as its own block first. No tracked Markdown file has the
    shape: cmark-gfm and `markdown-it-py` agree on code block bodies across all
    5,561 tracked files. This test pins the oracle's side so a parser upgrade
    that closes the gap fails here and prompts a re-measurement.
    """

    def test_oracle_reads_the_ordered_marker_as_a_list(self) -> None:
        assert _MD.render("[foo]: /url\n2. bar\n") == '<ol start="2">\n<li>bar</li>\n</ol>\n'
