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
which is the defect that tool exists to repair. Raw HTML blocks and a fence
ending when the document dedents out of its list item are known, pre-existing
limitations. Do not widen these cases into those areas without deciding what
the intended behavior is first.
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


# Each case is named for the CommonMark rule it exercises. The four rules the
# scanners had wrong were reported in review and confirmed here; the rest guard
# the opposite direction, that the fix did not make the scanners permissive.
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
}


# Randomized differential fuzzing.
#
# The curated cases above each pin one rule. The fuzzer answers the question
# they cannot: what is left. It generates small documents from the constructs
# that interact with list containers and compares against the same oracle.
#
# The residual is one named family, not noise. A fenced code block inside a
# list item ends, in CommonMark, when the document dedents out of that item;
# these scanners track a block's lifetime independently of its container's, so
# they keep such a block open. That is pre-existing behavior, unchanged by the
# container work, and it accounts for the great majority of the counts below.
# Raw HTML blocks swallowing a fence are the other known cause.
#
# Treat these as a ratchet in the repository's usual sense: a regression pushes
# a count up and fails, and work that closes part of the family lowers them.
# Re-measure rather than editing a number to make a run pass.
_FUZZ_INDENTS = ("", " ", "  ", "   ", "    ", "     ", "      ", "\t")
_FUZZ_BULLETS = ("-", "*", "+")
_FUZZ_ORDERED = ("1.", "2.", "01.", "003.", "1)", "10.", "9)")

# Measured against `random_documents` and `prose_lint._blank_fenced_blocks`
# at the commit that added this file. Of these, most are strict over-mask,
# which is the container-lifetime family described above: 32 of 37, 25 of 28,
# and 23 of 29 respectively.
FUZZ_BASELINE = {1729: 37, 20260826: 28, 4242: 29}
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
    return indent + rng.choice(("```", "~~~"))


def random_documents(seed: int, count: int = FUZZ_DOCUMENTS) -> list[str]:
    """Return *count* small Markdown documents, deterministic for *seed*."""
    rng = random.Random(seed)
    return [
        "\n".join(_fuzz_line(rng) for _ in range(rng.randrange(3, 9))) + "\n" for _ in range(count)
    ]
