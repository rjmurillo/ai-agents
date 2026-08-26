"""AST-based Markdown parsing utilities for session validation.

Provides structured extraction of Markdown tables and checklists using
markdown-it-py instead of fragile regex patterns. Simple patterns (SHAs,
dates, filenames) remain regex-based per the hybrid approach in issue #842.

Exit codes follow ADR-035 when used as a standalone script.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from markdown_it import MarkdownIt
from markdown_it.token import Token


@dataclass(frozen=True)
class ChecklistMatch:
    """Result of searching for a checklist item in a Markdown table."""

    complete: bool
    evidence: str


@dataclass
class TableRow:
    """A single parsed row from a Markdown table."""

    cells: list[str] = field(default_factory=list)


@dataclass
class ParsedTable:
    """A parsed Markdown table with headers and rows."""

    headers: list[str] = field(default_factory=list)
    rows: list[TableRow] = field(default_factory=list)


@dataclass(frozen=True)
class CellSegment:
    """One inline run inside a table cell.

    ``code`` marks a span written between backticks. A caller that treats a
    code span as documentation rather than as content has to tell the two
    apart, and only the token stream knows which is which. Keeping that
    distinction here, instead of a policy decision about which spans matter,
    leaves the policy with the caller that owns it.
    """

    content: str
    code: bool


@dataclass(frozen=True)
class TableCell:
    """A table cell's inline segments and its 1-based source line."""

    segments: tuple[CellSegment, ...]
    line: int

    @property
    def text(self) -> str:
        """The cell's rendered text, code spans included."""
        return "".join(segment.content for segment in self.segments)


@dataclass
class Section:
    """A Markdown section with heading level, title, and body content."""

    level: int
    title: str
    body: str


_FOOTNOTE_REFERENCE_RE = re.compile(r"\[\^[^\]\n]+\]")


class MarkdownNestingError(ValueError):
    """Raised when input nests past the parser's ``maxNesting`` limit.

    markdown-it stops emitting block tokens once container nesting reaches
    ``maxNesting`` and silently discards the rest of the input (see
    ``ParserBlock.tokenize``: it sets ``state.line = endLine`` and breaks). A
    code-stripping pass over a truncated token stream leaves the dropped,
    deeply-nested fenced code unblanked, so a ``vendor-portability`` marker or
    an example path hidden that deep would leak into the prose the caller
    scans. Refusing the file keeps the gate fail-closed: input the parser
    cannot fully represent is an incomplete scan, not clean prose.
    """


def _create_parser(max_nesting: int | None = None) -> MarkdownIt:
    """Create a configured markdown-it parser with table support.

    ``max_nesting`` overrides the CommonMark default only for the bounded
    second parse in :func:`_raise_if_nesting_truncated`. The primary parse keeps
    the default so its recursion stays bounded; the limit exists to stop a
    pathologically nested document from exhausting the stack, and raising it for
    the primary parse would reintroduce that denial-of-service vector.
    """
    md = MarkdownIt("commonmark").enable("table")
    if max_nesting is not None:
        md.options["maxNesting"] = max_nesting
    return md


# Block token types whose source lines are code, not prose. ``fence`` covers
# ```` ``` ```` and ``~~~`` blocks; ``code_block`` covers indented code. Both
# are resolved by the CommonMark parser, which tracks fence termination,
# blockquote depth, and list-relative indentation that a line-based scanner
# gets wrong.
_CODE_BLOCK_TOKEN_TYPES = frozenset({"fence", "code_block"})

# The above, widened with raw HTML blocks. A separate constant, not a
# replacement: `blank_code_block_lines` deliberately keeps HTML block content
# visible (`test_keeps_html_block` in tests/test_markdown_parser.py pins this
# for `check_skill_md_portability.py`'s `_strip_code`, which needs an unquoted
# `src=` path inside an `<img>` tag to stay scannable). A caller matching a
# prose-only pattern, like `check_adr_lifecycle.py`'s `## Status` heading
# search, needs the opposite: an HTML comment or `<details>` block is not
# prose either, and a status-shaped line inside one must not be read as the
# record's own declared status.
_NON_PROSE_BLOCK_TOKEN_TYPES = _CODE_BLOCK_TOKEN_TYPES | frozenset({"html_block"})


def _block_token_shape(tokens: list) -> list:
    """Structural fingerprint of the block token stream.

    Inline nesting lives inside an ``inline`` token's ``children`` and is
    excluded here, so deeply-nested emphasis or links (which cannot hide a code
    block) do not trigger a refusal. Only block-level truncation, which changes
    which lines a code-stripping pass blanks, changes this fingerprint.
    """
    return [
        (token.type, token.tag, token.level, tuple(token.map) if token.map else None)
        for token in tokens
    ]


def _raise_if_nesting_truncated(
    markdown: str, tokens: list, md: MarkdownIt
) -> None:
    """Fail closed when the primary parse dropped content at ``maxNesting``.

    The primary token stream cannot reveal truncation on its own: markdown-it
    caps reported nesting at ``maxNesting - 1`` whether the input stopped one
    level below the limit (complete) or ran past it (truncated). A bounded
    second parse at a higher limit disambiguates. If raising the limit changes
    the block structure, the primary parse was truncated and the file is
    refused. Content nesting past the second limit diverges further still, so
    the check never passes by merely moving the cliff, and the second parse
    stays bounded so no denial-of-service vector reopens.

    The second parse runs only when the primary reached ``maxNesting - 1``. The
    committed corpus peaks at level 9, far below the limit, so this path never
    fires on real files and adds no cost to a normal scan.
    """
    if not tokens:
        return
    max_nesting = md.options["maxNesting"]
    if max(token.level for token in tokens) < max_nesting - 1:
        return
    deep = _create_parser(max_nesting * 2)
    if _block_token_shape(tokens) != _block_token_shape(deep.parse(markdown)):
        raise MarkdownNestingError(
            f"Markdown nests past the parser limit (maxNesting={max_nesting}); "
            "the document cannot be fully scanned and is refused (issue #3499)."
        )


def _blank_matching_token_lines(
    lines: list[str], tokens: list[Token], token_types: frozenset[str]
) -> None:
    """Blank, in place, every line a token whose type is in ``token_types``
    spans. Preserves ``lines``' length and every other entry, so a caller
    matching against the result keeps stable line numbers.

    The genuinely shared step between `_blank_block_lines` (used only by
    `blank_code_block_lines`) and `blank_non_prose_block_lines`: both parse
    once, then run this same loop against their own token-type set. An
    earlier revision had `blank_non_prose_block_lines` reimplement this loop
    inline once it grew its own inline-comment masking pass ahead of it,
    which made `_blank_block_lines`'s "shared" claim false; Copilot found the
    stale claim on PR #5230 round 17 (`scripts/utils/markdown_parser.py:180`
    at the time). Extracting the loop here, rather than narrowing the
    docstring, keeps the two functions' block-blanking behavior from
    drifting apart the next time either one changes.
    """
    line_count = len(lines)
    for token in tokens:
        if token.type not in token_types or token.map is None:
            continue
        start, end = token.map
        for index in range(max(start, 0), min(end, line_count)):
            lines[index] = ""


def _blank_block_lines(markdown: str, token_types: frozenset[str]) -> str:
    """Parse ``markdown`` once and blank every line CommonMark attributes to
    a block whose type is in ``token_types``, via `_blank_matching_token_lines`.
    Used by `blank_code_block_lines`; `blank_non_prose_block_lines` parses
    separately (it needs the token stream for its own inline-comment masking
    pass too) and calls `_blank_matching_token_lines` directly on the result.

    Any exception the parser raises propagates to the caller, which must not
    treat a parse failure as clean prose. Failing closed here is deliberate: a
    silent empty return would let an unparseable file bypass the calling
    gate. For the same reason, input that nests past the parser's
    ``maxNesting`` limit raises :class:`MarkdownNestingError` rather than
    being scanned from a silently truncated token stream.
    """
    md = _create_parser()
    tokens = md.parse(markdown)
    _raise_if_nesting_truncated(markdown, tokens, md)
    lines = markdown.split("\n")
    _blank_matching_token_lines(lines, tokens, token_types)
    return "\n".join(lines)


def blank_code_block_lines(markdown: str) -> str:
    """Return ``markdown`` with fenced and indented code block lines blanked.

    Every source line that CommonMark attributes to a fenced or indented code
    block, including the fence marker lines, is replaced by an empty string.
    Line count and every non-code line, including HTML blocks, are preserved,
    so a caller that matches against the result keeps stable line numbers.

    Inline code spans are left intact; strip those separately when needed.

    HTML blocks are deliberately NOT blanked (see `blank_non_prose_block_lines`
    for a caller that needs them blanked too): `check_skill_md_portability.py`'s
    `_strip_code` depends on HTML content staying visible to catch a
    portability defect, an unquoted `src=` path, hiding inside an `<img>` tag
    (`test_keeps_html_block` in tests/test_markdown_parser.py pins this).
    """
    return _blank_block_lines(markdown, _CODE_BLOCK_TOKEN_TYPES)


def blank_non_prose_block_lines(markdown: str) -> str:
    """Return ``markdown`` with fenced/indented code and raw HTML content
    blanked, at both block and inline granularity.

    The block half has the same contract as `blank_code_block_lines`, widened
    to also blank HTML blocks (CommonMark's ``html_block`` token). Use this
    instead when the caller matches a prose-only pattern that must not be
    read out of an HTML comment or a `<details>` block: `check_adr_lifecycle.py`'s
    `_status_prose` needs exactly this, since a lifecycle-status-shaped line
    inside an HTML comment is documentation about status, not a declaration
    of it.

    A block-level HTML comment (`<!--` starting its own line) is a distinct
    `html_block` token and is blanked whole-line by the block half above. An
    HTML comment that instead opens mid-paragraph (``prose <!--``) is not a
    block at all: CommonMark tokenizes it as an ``html_inline`` child of the
    paragraph's ``inline`` token, and that span can legally cross source
    lines while the paragraph itself stays open, because only a handful of
    constructs interrupt a paragraph (a blank line, an ATX heading, a list
    marker, and similar; CommonMark spec section 4.9) and neither the
    comment's own `-->` nor its hidden content is one of them. A
    `**Status**: Accepted` line placed inside such a comment renders
    invisible to a human reader on GitHub or any other CommonMark renderer,
    while a raw-text regex scan over this function's block-only output would
    still read it as the record's declared status, since paragraph lines
    were left untouched. Copilot found this gap on PR #5230, one layer under
    the block-level HTML comment gap the block half closes. Verified
    empirically: parsing ``"prose <!--\\n**Status**: Accepted\\n-->\\n"``
    produces one ``html_inline`` child token whose content is the entire
    multi-line span, confirming a renderer treats it as one hidden unit
    (`test_hides_a_multiline_inline_html_comment_status`,
    tests/test_markdown_parser.py).

    The inline half derives its masked ranges from the parser's own
    ``html_inline`` tokens (`_html_comment_inline_ranges`), rather than
    re-scanning raw text for `<!--`/`-->`. An earlier revision of this fix
    used a hand-rolled substring scan (`_mask_inline_html_comments`, since
    removed) that could not tell a real comment opener from the same three
    characters appearing inside a backtick code span: `` `<!--` `` followed
    by `**Status**: Proposed` is CommonMark raw text (a `code_inline` token
    holding the literal `<!--`), not a comment, but the substring scan
    entered "in comment" state anyway and masked the real status that
    followed until the next `-->` anywhere in the document. Copilot found
    this on PR #5230 round 16. The parser has already resolved this
    precedence correctly by the time tokens exist (verified empirically:
    parsing `` "`<!--` **Status**: Proposed" `` produces a `code_inline`
    token holding `<!--`, and a separate `strong_open`/text/`strong_close`
    for the status, with no `html_inline` token at all), so reading its
    decision instead of re-deriving it sidesteps the whole class of
    precedence bugs a hand-rolled scanner is exposed to.
    """
    md = _create_parser()
    tokens = md.parse(markdown)
    _raise_if_nesting_truncated(markdown, tokens, md)
    characters = list(markdown)
    for start, end in _html_comment_inline_ranges(tokens, markdown):
        _mask_range(characters, start, end)
    lines = "".join(characters).split("\n")
    _blank_matching_token_lines(lines, tokens, _NON_PROSE_BLOCK_TOKEN_TYPES)
    return "\n".join(lines)


def _cell_text(content: str) -> str:
    """Normalize table cell text for validation consumers."""
    return _FOOTNOTE_REFERENCE_RE.sub("", content).strip()


def parse_tables(markdown: str) -> list[ParsedTable]:
    """Extract all tables from Markdown content using AST parsing.

    Args:
        markdown: Raw Markdown text.

    Returns:
        List of ParsedTable objects with headers and data rows.
    """
    md = _create_parser()
    tokens = md.parse(markdown)
    tables: list[ParsedTable] = []

    i = 0
    while i < len(tokens):
        if tokens[i].type == "table_open":
            table = _extract_table(tokens, i)
            if table is not None:
                tables.append(table)
            # Skip to table_close
            while i < len(tokens) and tokens[i].type != "table_close":
                i += 1
        i += 1

    return tables


def _inline_markdown_links(token: Token) -> list[str]:
    """Return rendered .md link targets from one inline token."""
    references: list[str] = []
    for child in token.children or []:
        if child.type != "link_open":
            continue
        href = child.attrGet("href")
        if isinstance(href, str) and href.endswith(".md"):
            references.append(href)
    return references


def _table_lookup_references(
    tokens: list[Token],
) -> tuple[list[str], set[int]]:
    """Return file-column references and occupied table source lines."""
    references: list[str] = []
    table_lines: set[int] = set()
    in_body = False
    cell_index = -1

    for token in tokens:
        if token.type == "tbody_open":
            in_body = True
            continue
        if token.type == "tbody_close":
            in_body = False
            continue
        if token.type == "tr_open":
            cell_index = -1
            if token.map:
                table_lines.update(range(token.map[0], token.map[1]))
            continue
        if token.type in {"th_open", "td_open"}:
            cell_index += 1
            continue
        if token.type != "inline" or not in_body or cell_index != 1:
            continue

        link_targets = _inline_markdown_links(token)
        if link_targets:
            references.extend(link_targets)
            continue
        bare_target = token.content.strip()
        if bare_target:
            references.append(
                bare_target
                if bare_target.endswith(".md")
                else f"{bare_target}.md"
            )

    return references, table_lines


def _ignored_block_lines(tokens: list[Token]) -> set[int]:
    """Return source lines rendered as code or HTML blocks."""
    ignored: set[int] = set()
    for token in tokens:
        if token.type not in {"fence", "code_block", "html_block"}:
            continue
        if token.map:
            ignored.update(range(token.map[0], token.map[1]))
    return ignored


def _root_paragraph_lines(tokens: list[Token]) -> set[int]:
    """Return source lines owned by top-level inline blocks."""
    lines: set[int] = set()
    for token in tokens:
        if token.type == "inline" and token.level == 1 and token.map:
            lines.update(range(token.map[0], token.map[1]))
    return lines


def _mask_range(
    characters: list[str],
    start: int,
    end: int,
) -> None:
    """Blank a source range without changing line positions."""
    for index in range(start, end):
        if characters[index] != "\n":
            characters[index] = " "


def _next_unescaped_backtick(
    line: str,
    start: int,
) -> tuple[int, int] | None:
    """Return the next backtick run that CommonMark can open."""
    for run in re.finditer(r"`+", line[start:]):
        absolute_start = start + run.start()
        prefix = line[:absolute_start]
        backslashes = len(prefix) - len(prefix.rstrip("\\"))
        if backslashes % 2 == 0:
            return absolute_start, len(run.group(0))
    return None


def _line_start_offsets(markdown: str) -> list[int]:
    """Absolute character offset where each ``str.split("\\n")``-indexed line
    begins.

    ``offsets[i]`` is the index into ``markdown`` of line ``i``'s first
    character, consistent with `_blank_block_lines`'s line numbering
    (``markdown.split("\\n")``, not ``str.splitlines()``; the schemas differ
    by the trailing empty element ``split`` keeps when the string ends in a
    newline).
    """
    lines = markdown.split("\n")
    offsets = [0]
    for line in lines[:-1]:
        offsets.append(offsets[-1] + len(line) + 1)
    return offsets


def _is_backslash_escaped(markdown: str, pos: int) -> bool:
    """True if CommonMark's backslash-escape rule applies to
    ``markdown[pos]``.

    Counts the consecutive backslashes immediately before ``pos``. An odd
    count means the final backslash pairs with and escapes this character;
    an even count (including zero) means every backslash has already paired
    with another backslash, so this character is unescaped. The same parity
    rule as `_next_unescaped_backtick` (`len(prefix) -
    len(prefix.rstrip("\\\\"))`), but walked backward one character at a
    time instead of slicing `markdown[:pos]`: `_next_unescaped_backtick`
    slices a single already-extracted line, bounded by that line's length,
    while this function is called from `_find_unescaped_occurrence`'s retry
    loop once per rejected candidate against the WHOLE document. Slicing
    there copies an ever-larger prefix on every rejection, so a document
    with N backslash-escaped decoys sharing the real token's content costs
    O(N) slices of growing size, O(N^2) overall (CWE-400): confirmed by
    timing the two implementations against 1000/2000/4000/8000 escaped
    decoys before an unescaped tail match, where the slice-based version's
    wall time roughly quadrupled on each doubling (0.6ms/1.7ms/6.1ms/21.4ms)
    while a backward scan grew linearly (0.26ms/0.56ms/1.4ms/3.0ms). Walking
    backward touches only the backslash run immediately preceding `pos`,
    which is bounded by that run's own length, not by how far into the
    document `pos` sits or how many earlier candidates were rejected. Found
    by Copilot on PR #5323.
    """
    count = 0
    i = pos - 1
    while i >= 0 and markdown[i] == "\\":
        count += 1
        i -= 1
    return count % 2 == 1


def _find_exact_backtick_run(
    markdown: str,
    run_length: int,
    start: int,
    end: int,
    *,
    require_unescaped: bool = False,
) -> int:
    """First position in ``markdown[start:end]`` of a backtick run whose
    length is EXACTLY ``run_length``, or -1 if none exists.

    Mirrors CommonMark's own code-span delimiter rule (spec section 6.1): a
    "backtick string" is a maximal run of backtick characters, and a code
    span's opening and closing delimiters must be backtick strings of equal
    length. A naive backtick-run search would happily
    match the first ``run_length`` backticks of a LONGER run (for example
    matching a single backtick inside a run of three), which is not what
    markdown-it itself does when choosing delimiters. Rejecting a candidate
    whose neighboring character is also a backtick, and retrying forward,
    keeps this in step with the parser's own rule without needing to
    re-derive the rest of CommonMark's inline precedence.

    ``require_unescaped``, set only by the OPENING-delimiter caller in
    `_html_comment_inline_ranges`, additionally rejects a candidate
    immediately preceded by an odd number of backslashes. A backslash-escaped
    backtick in ordinary text (`` \\` ``) is a literal backtick character, not
    a delimiter that can open a code span: markdown-it resolves it to a plain
    `text` token with no `code_inline` counterpart, so treating it as an
    opener finds a position the parser itself never treated as one. The
    CLOSING-delimiter caller in `_code_span_end` MUST NOT set this, because
    CommonMark backslash escapes do not apply inside code span content (spec
    6.1): a closing backtick run may legitimately follow a literal backslash
    that is part of the code's own text (verified empirically: `` `a\\\\`
    more `` tokenizes as `code_inline("a\\\\")`, a code span whose content
    ends in two literal backslashes right before the real closing backtick),
    and rejecting that closer would search past the span's real end.

    Without this check, an opening lookup can land on an escaped backtick and
    `_code_span_end` then treats the following REAL opening backtick as if it
    were the closer, shrinking the "span" to a few characters and leaving the
    cursor short of the real code span's true end. If that real code span's
    own content duplicates a later HTML comment's content, the subsequent
    `html_inline` search (which starts from that too-short cursor) matches
    the decoy inside the code span instead of the real, later comment.
    Verified empirically: parsing `` "\\\\` `<!-- x -->` <!-- x -->\\n" ``
    produces `text("\\` ")`, `code_inline("<!-- x -->")`, `text(" ")`,
    `html_inline("<!-- x -->")`; `blank_non_prose_block_lines` on that input
    blanked the code span's own visible text instead of the real trailing
    comment, which stayed completely readable, before this fix. Copilot
    found this on PR #5230 round 21, marked Mandatory.
    """
    target = "`" * run_length
    pos = start
    while True:
        idx = markdown.find(target, pos, end)
        if idx < 0:
            return -1
        preceded_by_backtick = idx > 0 and markdown[idx - 1] == "`"
        after = idx + run_length
        followed_by_backtick = after < len(markdown) and markdown[after] == "`"
        if (
            not preceded_by_backtick
            and not followed_by_backtick
            and not (require_unescaped and _is_backslash_escaped(markdown, idx))
        ):
            return idx
        pos = idx + 1


def _code_span_end(markdown: str, markup: str, start: int, end: int) -> int:
    """End offset (exclusive) of the ``code_inline`` span whose opening
    delimiter begins at ``start``, or -1 if it cannot be located.

    Locates the span by delimiter structure alone, the backtick run
    ``markup`` recorded on the token, never by searching for the token's
    own (possibly non-verbatim) ``.content``. An earlier revision searched
    for `.content` with an additional check that a candidate match was
    backtick-flanked (`_find_markup_anchored_occurrence`, since removed).
    That check proves a match is flanked by SOME backtick run of the right
    length; it does not prove the match belongs to the child currently
    being processed rather than a different, later `code_inline` sibling
    whose own (also normalized) content happens to coincide. `` `a\\nb`
    <!-- a b --> `a b` `` tokenizes as `code_inline("a b")` (normalized
    from the newline-joined "a\\nb"), `text(" ")`, `html_inline("<!-- a b
    -->")`, `text(" ")`, `code_inline("a b")` (the second span, genuinely
    "a b" verbatim): searching for the first `code_inline` child's content
    "a b" found it anchored inside the SECOND code span instead of the
    first (whose own raw text never contains "a b" as a substring at all),
    advancing the cursor past the real comment in between and leaving it
    completely unmasked. Copilot found this on PR #5230 round 20. Verified
    empirically: `blank_non_prose_block_lines("`a\\nb` <!-- a b --> `a
    b`\\n")` returned the input completely unmodified before this fix.

    Locating by delimiter alone has no content to search for and therefore
    no content to get wrong: the opening run is exactly where the caller
    says it is, and the closing run is the next backtick run of the same
    length after it, which is CommonMark's own definition of where a code
    span ends. No child's raw text is ever inspected, so no other child's
    coincidentally similar content can be mistaken for it.
    """
    open_end = start + len(markup)
    close_start = _find_exact_backtick_run(markdown, len(markup), open_end, end)
    if close_start < 0:
        return -1
    return close_start + len(markup)


def _find_unescaped_occurrence(
    markdown: str, content: str, start: int, end: int
) -> int:
    """First position in ``markdown[start:end]`` where ``content`` occurs and
    is not backslash-escaped, or -1 if none exists.

    Used only for an ``html_inline`` child's ``.content``, which CommonMark
    guarantees is always a verbatim copy of the source starting at ``<``, with
    no separate delimiter to strip. A backslash immediately before that ``<``
    escapes it (spec section 2.4): markdown-it then tokenizes the position as
    plain `text`, never as `html_inline`, so a REAL `html_inline` token's own
    start position can never itself be backslash-escaped. Rejecting an
    escaped candidate and retrying forward therefore never skips the real
    match; it only skips positions the parser itself never treated as one.

    Without this check, an unqualified `str.find` can bind an `html_inline`
    child's content to an EARLIER escaped decoy sharing the same raw text
    instead of the child's own later, real position. `` "prose \\<!--\\n"
    "**Status**: Accepted\\n--> more <!--\\n**Status**: Accepted\\n-->\\n" ``
    tokenizes as `text("prose <!--")` (the escaped comment opener, now a
    literal `<!--` with no separate token), `strong_open`/text/`strong_close`
    for the un-hidden `**Status**: Accepted` that follows it (parsing
    continues normally since no comment ever opened), `text("--> more ")`,
    then the REAL `html_inline("<!--\\n**Status**: Accepted\\n-->")`. A bare
    `find` for that content matches the FIRST, escaped occurrence (the
    backslash is simply skipped over, since `find` has no notion of
    escaping), masking the VISIBLE decoy prose while leaving the REAL,
    later comment's hidden `**Status**: Accepted` completely unmasked,
    exactly the status-forgery bypass this function exists to prevent.
    Verified empirically: `blank_non_prose_block_lines` on this input
    blanked the decoy's visible text and left the real comment's hidden
    status fully readable, before this fix. Copilot found this on PR #5230
    round 21 (delivered as a suppressed comment alongside the round-21
    Mandatory finding on the opening backtick lookup), citing the same
    escape-parity gap one branch over.
    """
    pos = start
    while True:
        idx = markdown.find(content, pos, end)
        if idx < 0:
            return -1
        if not _is_backslash_escaped(markdown, idx):
            return idx
        pos = idx + 1


def _html_comment_inline_ranges(
    tokens: list[Token],
    markdown: str,
) -> list[tuple[int, int]]:
    """Absolute (start, end) ranges covered by ``html_inline`` HTML comments.

    Reads the parser's own ``html_inline`` child tokens rather than
    re-scanning raw text for `<!--`/`-->`: the parser has already resolved
    CommonMark's precedence between an HTML comment and a backtick code
    span by the time these tokens exist, and a hand-rolled substring scan
    for the same thing is exposed to getting that precedence wrong (see
    `blank_non_prose_block_lines`'s docstring for the concrete Copilot
    finding this replaced). Only tokens whose content opens with `<!--` are
    returned: a bare inline tag such as `<b>` or `<img>` is not a comment,
    its enclosed text still renders, and masking it would hide content a
    reader can actually see.

    Each parent ``inline`` token's own ``.map`` gives the source line range
    its raw text spans; a child's exact character offset within that range
    is recovered by searching for the child's own matched text
    (``child.content``, which for a comment already includes any embedded
    newlines) starting from a cursor that only advances, so two identical
    comments in the same paragraph resolve to two distinct ranges rather
    than the first one twice.

    The cursor advances past every ``html_inline``/``code_inline`` child in
    source order, not only ones that turn out to be comments: an earlier
    revision searched only among ``html_inline`` children, so a preceding
    ``code_inline`` sibling whose own content happened to share bytes with a
    later real comment could steal the match. `` `<!-- x -->` <!-- x --> ``
    tokenizes as `code_inline("<!-- x -->")`, `text(" ")`,
    `html_inline("<!-- x -->")`; searching for the `html_inline` child's
    content from the start of the paragraph without first having advanced
    past the `code_inline` child's own identical text found the FIRST
    occurrence, inside the backticks, and masked visible code while leaving
    the real comment (and whatever it hides) untouched. Copilot found this
    on PR #5230 round 17, marked Mandatory.

    Only `html_inline` and `code_inline` children are consulted at all;
    every other child type (chiefly `text`, but also markup tokens such as
    `strong_open` whose own content is empty) is skipped entirely. An
    earlier revision searched every child's content regardless of type,
    reasoning that a decoy needed consuming in source order whatever kind
    of token carried it. That reasoning does not hold for `text`:
    markdown-it-py resolves HTML entities and backslash escapes in text
    content, so `&amp; ` decodes to `.content == "& "`, a string that need
    not appear anywhere near the text token's true source position.
    `find("& ", cursor, span_end)` can then match a later, unrelated
    literal `& ` that happens to sit after a real multiline comment,
    advancing the cursor past that comment; the subsequent search for the
    comment's own `html_inline` content then starts too late to find it,
    `found < 0` short-circuits the loop with no range recorded, and the
    comment's hidden `**Status**: Accepted` is never masked. Verified
    empirically: `blank_non_prose_block_lines("&amp; <!--\\n"
    "**Status**: Accepted\\n--> & tail\\n")` left `**Status**: Accepted`
    fully visible in the output before this fix. Copilot found this on PR
    #5230 round 18, marked Mandatory, citing CWE-20.

    A `code_inline` child's position is located by its DELIMITER structure
    (`_code_span_end`, using the backtick run recorded in `child.markup`),
    never by searching for its `.content`. Two rounds tried
    content-based search for `code_inline` and both were wrong: round 18
    reasoned CommonMark code spans only ever trim boundary whitespace, so
    any residual difference from raw source stays a proper substring at
    the same offset; that missed an embedded (non-boundary) line ending
    collapsing to a space, a real substitution, not trimming (round 19).
    Round 19's fix required a content match to be backtick-flanked, which
    proves a candidate sits inside SOME code span of the right delimiter
    length; it does not prove that code span is the one currently being
    processed, so a LATER sibling `code_inline` whose own (also possibly
    normalized) content happens to coincide can still steal the match. ``
    `a\\nb` <!-- a b --> `a b` `` tokenizes as `code_inline("a b")`
    (normalized from "a\\nb"), `text(" ")`, `html_inline("<!-- a b -->")`,
    `text(" ")`, `code_inline("a b")` (the second span, genuinely "a b"
    verbatim): searching for the FIRST code_inline's content "a b" found
    it anchored inside the SECOND, later code span instead, advancing the
    cursor past the real comment in between and leaving it fully
    unmasked. Copilot found this on PR #5230 round 20. Verified
    empirically: `blank_non_prose_block_lines("`a\\nb` <!-- a b -->
    `a b`\\n")` returned the input completely unmodified before this fix.
    Locating a code span by its opening and closing DELIMITERS, rather
    than by any content string, has no content to search for and
    therefore no content collision is possible with any other child,
    earlier or later: see `_code_span_end`'s docstring.
    """
    line_offsets = _line_start_offsets(markdown)
    ranges: list[tuple[int, int]] = []
    for token in tokens:
        if token.type != "inline" or not token.children or token.map is None:
            continue
        start_line, end_line = token.map
        span_start = line_offsets[start_line]
        span_end = (
            line_offsets[end_line] if end_line < len(line_offsets) else len(markdown)
        )
        cursor = span_start
        for child in token.children:
            if child.type == "code_inline":
                markup = child.markup or ""
                if not markup:
                    continue
                open_start = _find_exact_backtick_run(
                    markdown, len(markup), cursor, span_end, require_unescaped=True
                )
                if open_start < 0:
                    continue
                span_close = _code_span_end(markdown, markup, open_start, span_end)
                if span_close < 0:
                    continue
                cursor = span_close
            elif child.type == "html_inline":
                content = child.content or ""
                if not content:
                    continue
                found = _find_unescaped_occurrence(markdown, content, cursor, span_end)
                if found < 0:
                    continue
                cursor = found + len(content)
                if content.startswith("<!--"):
                    ranges.append((found, cursor))
    return ranges


def _mask_inline_contexts(
    markdown: str,
    ignored_lines: set[int],
) -> list[str]:
    """Blank inline code and HTML comments outside ignored block lines."""
    characters = list(markdown)
    code_start: int | None = None
    code_length = 0
    in_comment = False
    offset = 0

    for line_number, line in enumerate(markdown.splitlines(keepends=True)):
        if line_number in ignored_lines:
            code_start = None
            code_length = 0
            in_comment = False
            offset += len(line)
            continue

        position = 0
        while position < len(line):
            if in_comment:
                close = line.find("-->", position)
                if close < 0:
                    _mask_range(characters, offset + position, offset + len(line))
                    break
                _mask_range(characters, offset + position, offset + close + 3)
                in_comment = False
                position = close + 3
                continue

            if code_start is not None:
                closing = next(
                    (
                        run
                        for run in re.finditer(r"`+", line[position:])
                        if len(run.group(0)) == code_length
                    ),
                    None,
                )
                if closing is None:
                    break
                closing_end = position + closing.end()
                _mask_range(characters, code_start, offset + closing_end)
                code_start = None
                code_length = 0
                position = closing_end
                continue

            comment_start = line.find("<!--", position)
            backtick = _next_unescaped_backtick(line, position)
            backtick_start = backtick[0] if backtick is not None else -1
            if comment_start >= 0 and (
                backtick_start < 0 or comment_start < backtick_start
            ):
                in_comment = True
                _mask_range(
                    characters,
                    offset + comment_start,
                    offset + comment_start + 4,
                )
                position = comment_start + 4
                continue
            if backtick is None:
                break
            code_start = offset + backtick_start
            code_length = backtick[1]
            position = backtick_start + code_length

        offset += len(line)

    return "".join(characters).splitlines()


def extract_lookup_references(markdown: str) -> list[str]:
    """Return .md targets from rendered lookup rows and table file cells."""
    md = _create_parser()
    environment: dict[str, object] = {}
    tokens = md.parse(markdown, environment)
    _raise_if_nesting_truncated(markdown, tokens, md)

    references, table_lines = _table_lookup_references(tokens)
    ignored_lines = _ignored_block_lines(tokens) | table_lines
    root_lines = _root_paragraph_lines(tokens) - ignored_lines

    for line_number, line in enumerate(
        _mask_inline_contexts(markdown, ignored_lines)
    ):
        if line_number not in root_lines:
            continue
        if not line.startswith("|"):
            continue
        inline_tokens = md.parseInline(line, environment)
        for token in inline_tokens:
            if token.type == "inline":
                references.extend(_inline_markdown_links(token))

    return references


def iter_table_cell_text(markdown: str) -> Iterator[TableCell]:
    """Yield the rendered text of every table cell with its source line.

    Only cells of tables the CommonMark parser actually recognises are
    emitted, which is the point. A line-based scanner that calls any
    pipe-shaped line a table row is wrong in both directions: it misses
    tables written without outer pipes, inside a blockquote, or indented
    under a list item, and it matches pipe-shaped prose that renders as a
    paragraph because it has no delimiter row.

    Each cell is yielded as its inline segments rather than as one string, so
    a caller can decide what a code span means to it. Emphasis contributes its
    text because the emphasis markers are not part of the rendered content.
    Fenced and indented code blocks and HTML comments never parse as tables,
    so they are excluded by construction rather than by a second stripping
    pass.

    Fails closed on input the parser cannot fully represent, for the reason
    given in :class:`MarkdownNestingError`.
    """
    md = _create_parser()
    tokens = md.parse(markdown)
    _raise_if_nesting_truncated(markdown, tokens, md)

    line = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "tr_open" and token.map:
            line = token.map[0] + 1
        elif (
            token.type in ("th_open", "td_open")
            and index + 1 < len(tokens)
            and tokens[index + 1].type == "inline"
        ):
            children = tokens[index + 1].children or []
            segments = tuple(
                CellSegment(content=child.content, code=child.type == "code_inline")
                for child in children
                if child.type in ("text", "code_inline")
            )
            yield TableCell(segments=segments, line=line)
            index += 1
        index += 1


def _extract_table(tokens: list, start: int) -> ParsedTable | None:
    """Extract a single table from the token stream starting at table_open."""
    table = ParsedTable()
    i = start + 1
    in_thead = False
    in_tbody = False
    current_row: list[str] = []

    while i < len(tokens):
        token = tokens[i]
        if token.type == "table_close":
            break
        if token.type == "thead_open":
            in_thead = True
        elif token.type == "thead_close":
            in_thead = False
        elif token.type == "tbody_open":
            in_tbody = True
        elif token.type == "tbody_close":
            in_tbody = False
        elif token.type == "tr_open":
            current_row = []
        elif token.type == "tr_close":
            if in_thead:
                table.headers = current_row
            elif in_tbody:
                table.rows.append(TableRow(cells=current_row))
        elif token.type in ("th_open", "td_open"):
            # Next token is inline with cell content
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                cell_content = _cell_text(tokens[i + 1].content)
                current_row.append(cell_content)
                i += 1  # skip inline token
            else:
                current_row.append("")
        i += 1

    return table


def find_checklist_item(markdown: str, pattern: str) -> ChecklistMatch:
    """Search Markdown tables for a row matching pattern with [x] checkbox.

    Parses all tables in the document using AST, then searches for rows
    where any cell matches the pattern (case-insensitive) and another cell
    contains a checked checkbox [x].

    Args:
        markdown: Raw Markdown text containing tables.
        pattern: Regex pattern to match against cell content.

    Returns:
        ChecklistMatch with complete=True and evidence text if found.
    """
    tables = parse_tables(markdown)
    compiled = re.compile(pattern, re.IGNORECASE)

    for table in tables:
        for row in table.rows:
            has_pattern_match = False
            has_checked = False
            evidence = ""

            for cell in row.cells:
                if compiled.search(cell):
                    has_pattern_match = True
                if "[x]" in cell.lower():
                    has_checked = True

            if has_pattern_match and has_checked:
                # Evidence is the last non-checkbox, non-pattern cell
                for cell in reversed(row.cells):
                    if "[x]" not in cell.lower() and not compiled.search(cell):
                        evidence = cell.strip()
                        break
                # Fallback: use the last cell
                if not evidence and row.cells:
                    evidence = row.cells[-1].strip()
                return ChecklistMatch(complete=True, evidence=evidence)

    return ChecklistMatch(complete=False, evidence="")


def parse_sections(markdown: str) -> list[Section]:
    """Extract heading-delimited sections from Markdown.

    Args:
        markdown: Raw Markdown text.

    Returns:
        List of Section objects with level, title, and body text.
    """
    md = _create_parser()
    tokens = md.parse(markdown)
    sections: list[Section] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.type == "heading_open":
            level = int(token.tag[1])  # h1 -> 1, h2 -> 2, etc.
            title = ""
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                title = tokens[i + 1].content.strip()

            # Advance past heading_close to find body tokens
            j = i + 1
            while j < len(tokens) and tokens[j].type != "heading_close":
                j += 1
            j += 1  # skip heading_close

            body_start_line = None
            if j < len(tokens):
                start_map = tokens[j].map
                if start_map is not None:
                    body_start_line = start_map[0]

            # Find end of section (next heading of same or higher level, or EOF)
            body_end_line = None
            k = j
            while k < len(tokens):
                if tokens[k].type == "heading_open":
                    next_level = int(tokens[k].tag[1])
                    end_map = tokens[k].map
                    if next_level <= level and end_map is not None:
                        body_end_line = end_map[0]
                        break
                k += 1

            # Extract body from source lines
            if body_start_line is not None:
                lines = markdown.split("\n")
                end = body_end_line if body_end_line is not None else len(lines)
                body = "\n".join(lines[body_start_line:end]).strip()
            else:
                body = ""

            sections.append(Section(level=level, title=title, body=body))
            i = j
        else:
            i += 1

    return sections


def find_section(markdown: str, heading: str, level: int = 2) -> str | None:
    """Find a specific section by heading text and level.

    Args:
        markdown: Raw Markdown text.
        heading: Heading text to search for (case-insensitive).
        level: Heading level to match (default: 2 for ##).

    Returns:
        Section body text, or None if not found.
    """
    sections = parse_sections(markdown)
    heading_lower = heading.lower()
    for section in sections:
        if section.level == level and section.title.lower() == heading_lower:
            return section.body
    return None
