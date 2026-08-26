"""Randomized differential fuzzing for the two Markdown fence scanners.

Split out of `commonmark_fence_cases` when that module crossed the 500 line
taste ceiling. The split is along the seam the module already had: curated
cases and the oracle on one side, generated documents and their ratchets on
the other. Both suites import from both, and the baseline stayed at 575
rather than being raised, which is the repository rule for every counting
ratchet here.
"""

from __future__ import annotations

import random

# Randomized differential fuzzing.
#
# The curated cases in `commonmark_fence_cases` each pin one rule. The fuzzer answers the question
# they cannot: what is left. It generates small documents from the constructs
# that interact with list containers and compares against the same oracle.
#
# This description deliberately carries NO count. It named a single family, a
# fenced block outliving its list item, and went stale when rule 10 closed
# exactly that; it was then rewritten with an explicit total and went stale
# again when rule 15 closed most of it. A count duplicated in prose has now
# drifted twice, so `FUZZ_BASELINE` below is the single numeric source of
# truth. The residue's shape is described in the case module's docstring and
# NOT repeated here, because it has now been described wrongly twice: once as a
# lazy/empty pairing, and once as `both carry five-or-more columns of padding`
# under a sentence beginning `Measured`, when one of the two documents has a
# maximum of two columns and no empty item at all. A description asserted as
# measured and never re-measured is worse than none.
#
# Raw HTML is NOT among these: the generator emits no `<` at all
# across all 6,000 documents, so it cannot appear in this residue. The fuzz
# negative control pins raw HTML with a hand-written document instead.
#
# Treat these as a ratchet in the repository's usual sense: a regression pushes
# a count up and fails, and work that closes part of the residue lowers them.
# Re-measure rather than editing a number to make a run pass, and re-describe
# the residue when a rule changes what it is made of.
_FUZZ_INDENTS = ("", " ", "  ", "   ", "    ", "     ", "      ", "\t")
_FUZZ_BULLETS = ("-", "*", "+")
_FUZZ_ORDERED = ("1.", "2.", "01.", "003.", "1)", "10.", "9)")

# Measured against `random_documents` and `prose_lint._blank_fenced_blocks`,
# re-measured whenever a rule closes part of the residue.
#
# These are not comparable with figures recorded before rule 9, because the
# generator was widened at the same time to emit marker lines whose remainder
# is itself a block start. That family had produced a `--write` corruption the
# fuzzer could not reach. On the widened generator the counts were 212, 247 and
# 225; rule 10 (a block ends with its container) took them to what follows.
# Rule 11 (a setext underline ends its paragraph) took seed 20260826 from 6.
# Rule 12 (a marker line leaves paragraph state to its own remainder) took
# seed 20260826 from 5 and seed 4242 from 6.
#
# Figures before the Unicode-whitespace widening are not comparable with what
# follows either, for the same reason as the rule 9 discontinuity above: the
# generator emitted no Unicode whitespace at ALL, so a `--write` corruption on
# a closing fence carrying U+00A0 was invisible to every ratchet in the
# repository, corpus and fuzzer alike. Review found it, not the fuzzer, twice
# running. About 43 percent of documents per seed now carry U+00A0 or U+3000 in
# a closer or a marker remainder. Measured teeth: against the scanner as it
# stood before that fix, the widened generator diverges on 8, 12 and 8
# documents for seeds 1729, 4242 and 20260826, and three of those also mutate a
# well formed document on `--write`.
FUZZ_BASELINE = {1729: 1, 20260826: 0, 4242: 1}
FUZZ_DOCUMENTS = 2000


def _fuzz_line(rng: random.Random) -> str:
    kind = rng.randrange(9)
    indent = rng.choice(_FUZZ_INDENTS)
    if kind == 0:
        return ""
    if kind == 1:
        pad = rng.choice(_FUZZ_INDENTS[:6])
        # Draw order matters: it decides the document set, so keep the
        # marker draw ahead of the body draw as it has always been.
        marker = rng.choice(_FUZZ_BULLETS)
        return indent + marker + pad + rng.choice(("item", "", "robust", "\u00a0"))
    if kind == 2:
        pad = rng.choice(_FUZZ_INDENTS[:6])
        return indent + rng.choice(_FUZZ_ORDERED) + pad + rng.choice(("item", "", "text", "\u00a0"))
    if kind == 3:
        # The Unicode-whitespace suffixes are closer-position bait. A closing
        # fence may be followed only by spaces and tabs, and reading that with
        # `str.strip()` accepted U+00A0 as a blank info string, closed the
        # block early, and let `--write` append a fence to a well formed
        # document. No ratchet could see it: the generator emitted no Unicode
        # whitespace anywhere.
        return indent + rng.choice(
            ("```", "~~~", "````", "```py", "~~~~", "```\u00a0", "~~~\u00a0", "```\u3000")
        )
    if kind == 4:
        return indent + rng.choice(("prose text", "lazy line", "more words"))
    if kind == 5:
        return indent + rng.choice(("# H", "## H2"))
    if kind == 6:
        return indent + rng.choice(("***", "---", "___", "* * *", "- - -"))
    if kind == 7:
        return indent + rng.choice(("> quote", "code_ish()"))
    # Rule 9 territory: a marker whose remainder is itself a block start. This
    # family produced a `--write` corruption that review, not the fuzzer, found,
    # because the generator could not emit it. It can now.
    return indent + rng.choice(
        ("- ```", "- ~~~", "- - ```", "1. ~~~info", "- # h", "- - a", "* ```py")
    )


def random_documents(seed: int, count: int = FUZZ_DOCUMENTS) -> list[str]:
    """Return *count* small Markdown documents, deterministic for *seed*."""
    rng = random.Random(seed)
    return [
        "\n".join(_fuzz_line(rng) for _ in range(rng.randrange(3, 9))) + "\n" for _ in range(count)
    ]
