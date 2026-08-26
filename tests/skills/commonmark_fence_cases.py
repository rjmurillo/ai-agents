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
}
