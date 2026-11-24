"""Prose preparation for ``check_adr_supersession_citations.py``.

Blanks what cannot hold an ADR citation while keeping every offset, splits the
masked text into paragraph blocks, and counts quotes per line. The gate imports
these; nothing else does.

Different from the rule gate (``check_rule_adr_citations.py``) in two places,
both on purpose:

- Frontmatter. ADR records are parsed through
  ``scripts/hook_utilities/frontmatter_block.py``, which accepts a padded or
  four-dash fence. This module masks the block that same parser finds, so
  metadata the lifecycle gate reads as frontmatter is never read here as prose.
- Blocks. The rule gate starts a new block at a capitalised wrapped line, so a
  sentence soft-wrapped before ``ADR-080`` loses its first half. Here a block runs
  from one blank line, heading, list item, table row or quote to the next, so a
  wrap never splits a sentence. The sentence splitter still cuts at ``.``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]
for _path in (_REPO_ROOT, _SCRIPT_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from check_rule_adr_citations import (  # noqa: E402
    BLOCK_START_RE,
    CODE_SPAN_RE,
    FENCE_RE,
    HEADING_RE,
    blank,
)

from scripts.hook_utilities.frontmatter_block import split_frontmatter  # noqa: E402

Block = list[tuple[int, str]]


def _blank_span(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def mask_frontmatter(text: str) -> str:
    """Blank the leading frontmatter block, fences included, keeping every offset.

    An unclosed block is left as it is: the lifecycle gate reports it.
    """
    split = split_frontmatter(text)
    if not split.found:
        return text
    return _blank_span(text[: split.body_start]) + text[split.body_start :]


def mask_comments(text: str) -> str:
    """The rule gate's ``<!--.*?-->`` blanking, in one linear pass (no retries)."""
    parts, at = [], 0
    while (opened := text.find("<!--", at)) != -1:
        closed = text.find("-->", opened + 4)
        if closed == -1:
            break
        parts += [text[at:opened], _blank_span(text[opened : closed + 3])]
        at = closed + 3
    return "".join(parts) + text[at:]


def _soften_code_span(match: re.Match[str]) -> str:
    """Keep a code span's words (`superseded` is lineage), drop its delimiters,
    quotes and ADR ids: an id inside a span is still not a citation."""
    text = match.group(0).replace("`", " ").replace('"', " ")
    return re.sub(r"ADR-", "ADR_", text)


def mask_non_citations(text: str) -> str:
    """Blank what cannot hold a citation, preserving every offset."""
    text = FENCE_RE.sub(blank, mask_frontmatter(text))
    text = mask_comments(text)
    # The shared patterns import untyped, so pin the result type here.
    masked: str = CODE_SPAN_RE.sub(_soften_code_span, text)
    return masked


def paragraph_blocks(masked: str) -> list[Block]:
    """Blocks of ``(lineno, text)``; a block ends at a blank line or a heading,
    and a list item, table row or quote starts a new one."""
    found: list[Block] = []
    current: Block = []
    for number, line in enumerate(masked.split("\n"), start=1):
        if not line.strip() or HEADING_RE.match(line):
            current = []
            continue
        if not current or BLOCK_START_RE.match(line):
            current = []
            found.append(current)
        current.append((number, line))
    return found


def quote_counts(text: str) -> tuple[int, int]:
    """Straight double quotes and the curly open-minus-close balance in ``text``."""
    return text.count('"'), text.count("“") - text.count("”")


def paragraph_quotes(masked: str) -> list[tuple[int, int]]:
    """Per line (index 0 is line 1), quote counts over its paragraph so far; a
    sentence split can cut one quotation in two, a paragraph cannot."""
    counts: list[tuple[int, int]] = []
    straight = curly = 0
    for line in masked.split("\n"):
        if not line.strip():
            straight = curly = 0
        counts.append((straight, curly))
        more_straight, more_curly = quote_counts(line)
        straight, curly = straight + more_straight, curly + more_curly
    return counts
