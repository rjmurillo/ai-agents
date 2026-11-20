"""Cost bounds for scripts/validation/check_adr_supersession_citations.py.

Review round 6 measured quadratic time on adversarial ADR text: 9.9 s for one
16 KB sentence, 22.6 s for 2000 mention lines in one paragraph, and 9.1 s for
100 KB of unclosed ``<!--`` through the rule gate's comment regex. Each test
below runs one of those shapes far past its old cost under a pytest timeout,
and the comment masker is pinned to the rule gate's regex on inputs it can
handle, so the linear pass changes speed only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_adr_supersession_citations import (
    AUTHORITY,
    HISTORY,
    WINDOW,
    _mask_comments,
    citations_in,
)
from check_rule_adr_citations import COMMENT_RE, blank

from tests.validation.test_check_adr_supersession_citations import CORPUS


@pytest.mark.parametrize(
    "text",
    [
        "a <!-- ADR-080 governs --> b\n",
        "<!-- one -->\n<!-- two\nlines -->\ntail\n",
        "open <!-- never closed ADR-080\nmore\n",
        "<!-- a --> mid <!-- b\n",
        "<!--> not a comment --> x\n",
        "no comments at all\n",
        "<!---->\n<!-- x --->\n",
    ],
)
def test_comment_masking_matches_the_rule_gate_regex(text: str) -> None:
    assert _mask_comments(text) == COMMENT_RE.sub(blank, text)


@pytest.mark.timeout(10)
def test_unclosed_comment_openers_mask_in_linear_time() -> None:
    text = "<!-- " * 40_000 + "ADR-080 governs pins.\n"
    assert _mask_comments(text) == text


@pytest.mark.timeout(10)
def test_one_long_sentence_is_classified_in_linear_time() -> None:
    text = "ADR-080 governs pins and " * 2_000 + "more.\n"  # about 50 KB, one sentence
    found = citations_in("f.md", 107, text, CORPUS)
    assert len(found) == 2_000
    assert {c.kind for c in found} == {AUTHORITY}


@pytest.mark.timeout(10)
def test_many_lines_in_one_paragraph_are_classified_in_linear_time() -> None:
    text = "".join(f"line {n} cites ADR-080, which governs pins;\n" for n in range(15_000))
    found = citations_in("f.md", 107, text, CORPUS)
    assert len(found) == 15_000


def test_a_signal_beyond_the_window_is_not_read() -> None:
    """The documented limit: a history word more than WINDOW characters away."""
    filler = "x " * WINDOW
    near = citations_in("f.md", 107, "Historically ADR-080 governs pins.\n", CORPUS)
    far = citations_in("f.md", 107, f"Historically {filler}ADR-080 governs pins.\n", CORPUS)
    assert [c.kind for c in near] == [HISTORY]
    assert [c.kind for c in far] == [AUTHORITY]
