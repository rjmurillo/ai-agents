"""Shared CommonMark oracle for the two Markdown fence scanners.

Both `fix_fences.py` and `prose_lint.py` decide which lines sit inside a fenced
code block, and both must measure a fence marker's indent from its containing
list item rather than from column zero. The rules that govern that are easy to
state and easy to get subtly wrong, so the cases below are checked against
`markdown-it-py`, a CommonMark reference implementation and a declared
dependency of this repository, instead of against hand-written expectations.

Scope. This oracle covers list-container handling only. The scanners diverge
from CommonMark elsewhere on purpose: a fence carrying an info string inside an
open block is content to CommonMark but a mistaken closer to `fix_fences.py`,
which is the defect that tool exists to repair.

One known limitation is out of scope here: a raw HTML block (for example
`<example ...>`) swallows a following fence, so the scanners read a fence there
that CommonMark does not. Two others used to be listed and were implemented
instead, because in each case the argument for tolerating them was that the gap
only made the scanners miss a fence, and measurement showed the opposite. Both
left a block open past its real end, so `--write` appended a closing fence to
well-formed documents. Do not repeat that reasoning without measuring; see
rules 9 and 10 in `_ListContainers`.

What remains in the fuzz residue below is not one family. It is a handful of
deep interactions between lazy continuations, empty items, and five-or-more
columns of padding under nested markers.

Do not widen these cases into those areas without deciding what the intended
behavior is first. The fuzz baselines below are what bound them.
"""

from __future__ import annotations

import random

from markdown_it import MarkdownIt

_MD = MarkdownIt("commonmark")


def oracle_fence_lines(text: str) -> set[int]:
    """Return 0-indexed non-blank lines inside a CommonMark fenced code block.

    Blank lines are excluded because they carry no prose either way, so
    including them would measure the comparison rather than the scanner.
    """
    source = text.splitlines()
    inside: set[int] = set()
    for token in _MD.parse(text):
        if token.type == "fence" and token.map:
            start, stop = token.map
            inside.update(
                index for index in range(start, min(stop, len(source))) if source[index] != ""
            )
    return inside


# Each case is named for the CommonMark rule it exercises. `_ListContainers`
# carries eleven numbered rules and every one of them was a real defect first,
# most reported in review and the rest found by the fuzzer below; each was
# reproduced against the reference parser before being fixed. The remaining
# cases guard the opposite direction, that a fix did not make the scanners
# permissive. Keep this description and the rule numbering in step: an earlier
# version said four, and stayed at four while the count reached eleven.
CASES: dict[str, str] = {
    # Rule 1: a marker more than three columns past its container is code.
    "marker over indented is code": "    - literal\n      ```\n      x\n",
    # Rule 2: five or more columns of padding is not all indentation.
    "padding of five columns": "-     literal\n      ```\n      x\n      ```\n",
    "padding of four columns": "-    item\n     ```\n     x\n     ```\n",
    # Rule 3: an item with no content on its line still opens a container.
    "empty item opens a container": "-\n    ```\n    x\n    ```\nafter\n",
    "empty item then nested item": "-\n  - inner\n\n    ```\n    x\n    ```\nafter\n",
    # Rule 4: only a non-empty item, ordered at 1, may interrupt a paragraph.
    "ordered two cannot interrupt": "Some prose.\n2. literal\n    ~~~\n    x\n    ~~~\nafter\n",
    "ordered one can interrupt": "Some prose.\n1. item\n    ~~~\n    x\n    ~~~\nafter\n",
    "empty item cannot interrupt": "Some prose.\n-\n    ~~~\n    x\n    ~~~\nafter\n",
    "ordered two after a blank line": "Some prose.\n\n2. item\n    ~~~\n    x\n    ~~~\nafter\n",
    # Sync before classify: a dedent closes its container before the indent test.
    "dedent before a top level opener": "- item\n~~~\ncode\n    ~~~\nafter\n",
    # Guards against an over-permissive container model.
    "nested item fence": "- item\n  - nested:\n\n    ```bash\n    x\n    ```\n\nDone.\n",
    "top level four space marker": "Text.\n\n    ~~~\n\nAfter.\n",
    "four columns past the container": "- item\n\n      ~~~\n\nAfter.\n",
    "blank line inside an item": "- item\n\n    ~~~\n    x\n    ~~~\n\nDone.\n",
    # Rule 4 detail: leading zeros do not change an ordered list's start value.
    "leading zero starts at one": ("Some prose.\n01. item\n    ~~~\n    x\n    ~~~\nafter\n"),
    "three leading zeros start at one": (
        "Some prose.\n001. item\n     ~~~\n     x\n     ~~~\nafter\n"
    ),
    "leading zero three cannot interrupt": (
        "Some prose.\n003. item\n     ~~~\n     x\n     ~~~\nafter\n"
    ),
    # Rule 5: a thematic break matches the bullet grammar but is not an item.
    "thematic break of stars": "* * *\n    ~~~\n    x\n    ~~~\nafter\n",
    "thematic break of dashes": "- - -\n    ~~~\n    x\n    ~~~\nafter\n",
    # Rule 6: a lazy continuation may dedent without closing its item.
    "lazy paragraph continuation": (
        "  1.  A paragraph\nwith two lines.\n\n      ```\n      x\n      ```\nafter\n"
    ),
    # Rule 7: paragraph state follows blocks, measured against the container.
    "a fence ends the paragraph": (
        "Para text.\n~~~\ncode\n~~~\n2. next\n    ```\n    y\n    ```\nafter\n"
    ),
    "heading indented inside a list": (
        "- item\n  - nested\n    # Heading\n    2. next\n"
        "        ```\n        y\n        ```\nafter\n"
    ),
    "thematic break inside a list": (
        "- item\n  - nested\n    ***\n    2. next\n        ```\n        y\n        ```\nafter\n"
    ),
    "indented code is not a paragraph": "     ```\n - \n     ```\n",
    "a marker with no padding is prose": " +  item\n1)text\n      ~~~\n",
    # Rule 8: an item may begin with at most one blank line.
    "blank line closes an empty item": "-\n\n    ```\n    x\n    ```\n",
    "blank line closes an empty ordered item": "1)\n\n    ```\n    x\n    ```\n",
    "two blanks close an empty item": "-\n\n\n    ```\n    x\n    ```\n",
    "a blank keeps a non-empty item open": "- item\n\n    ```\n    x\n    ```\n",
    # Rule 9: a marker line's remainder is re-parsed inside the item.
    "backtick fence on the marker line": "- ```\n  x\n  ```\n\nEnd.\n",
    "tilde fence on the marker line": "- ~~~\n  x\n  ~~~\n\nEnd.\n",
    "fence with an info string on the marker line": ("1. ~~~info\n   x\n   ~~~\n\nEnd.\n"),
    "two markers then a fence on one line": "- - ```\n    x\n    ```\n\nEnd.\n",
    "a heading on the marker line": ("- # heading\n2. item\n      ```\n      x\n      ```\n"),
    "two markers on one line": "- - a\n      ```\n      x\n      ```\n",
    # Rule 11: a setext underline ends the paragraph above it.
    "setext h1 ends the paragraph": ("Title\n===\n2. item\n    ~~~\n    robust\n    ~~~\n"),
    "single equals is a setext underline": ("Title\n=\n2. item\n    ~~~\n    x\n    ~~~\n"),
    "setext h2 ends the paragraph": "Title\n---\n2. item\n    ~~~\n    x\n    ~~~\n",
    "equals with no paragraph is prose": ("\n===\n2. item\n    ~~~\n    x\n    ~~~\n"),
    # Five columns of padding leave four behind, so a marker-line fence is
    # indented code. Stripping that indent opened a fence in literal content.
    "padding of five before a marker-line fence": ("-     ```\n     x\n     ```\nafter\n"),
    "padding of five before a marker-line tilde": ("-     ~~~\n     x\n     ~~~\nafter\n"),
    "padding of two before a marker-line fence": "-  ```\n   x\n   ```\nafter\n",
    # A backtick opening fence may not carry a backtick in its info string.
    "backtick in a fence info string": ("para\n```lang`x`\nrobust significant\n```\nafter\n"),
    "backtick info on a marker line": "- ```lang`x`\n  robust\n",
    # An ordered marker is ASCII digits only; Python's `\d` is not.
    "arabic-indic digits are not a marker": ("\u0661. item\n\n    ~~~\n    robust\n    ~~~\n"),
    "devanagari digits are not a marker": ("\u0967. item\n\n    ~~~\n    x\n    ~~~\n"),
    "ascii digits are a marker": "1. item\n\n   ~~~\n   x\n   ~~~\n",
    # A marker line does not itself open a paragraph; its remainder decides.
    "nested ordered on the marker line": (
        "- 2. item\n\n        ~~~\n        x\n        ~~~\nafter\n"
    ),
    "nested ordered one on the marker line": (
        "- 1. item\n\n        ~~~\n        x\n        ~~~\nafter\n"
    ),
}


# Randomized differential fuzzing.
#
# The curated cases above each pin one rule. The fuzzer answers the question
# they cannot: what is left. It generates small documents from the constructs
# that interact with list containers and compares against the same oracle.
#
# This description used to name a single family, a fenced block outliving its
# list item, and was left stale for one commit after rule 10 closed exactly
# that. What remains is not one family and not much: a dozen documents across
# the three seeds, in deep interactions between lazy continuations, empty
# items, and five-or-more columns of padding under nested markers. Raw HTML
# blocks swallowing a fence are the other known cause and are what the fuzz
# negative control pins.
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
FUZZ_BASELINE = {1729: 1, 20260826: 1, 4242: 4}
FUZZ_DOCUMENTS = 2000


def _fuzz_line(rng: random.Random) -> str:
    kind = rng.randrange(9)
    indent = rng.choice(_FUZZ_INDENTS)
    if kind == 0:
        return ""
    if kind == 1:
        pad = rng.choice(_FUZZ_INDENTS[:6])
        return indent + rng.choice(_FUZZ_BULLETS) + pad + rng.choice(("item", "", "robust"))
    if kind == 2:
        pad = rng.choice(_FUZZ_INDENTS[:6])
        return indent + rng.choice(_FUZZ_ORDERED) + pad + rng.choice(("item", "", "text"))
    if kind == 3:
        return indent + rng.choice(("```", "~~~", "````", "```py", "~~~~"))
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
