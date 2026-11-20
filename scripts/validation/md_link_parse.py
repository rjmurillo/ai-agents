"""Pure markdown link-parsing helpers shared by the link checkers.

Moved out of ``check_adr_links.py`` so ``check_md_links.py`` can reuse them
without importing the ADR-number rules. ``check_adr_links`` re-exports every
name here, so existing callers and tests keep working unchanged.
"""

from __future__ import annotations

import re

# CommonMark caps fence indentation at three spaces
# (spec.commonmark.org/0.31.2/#fenced-code-blocks, quoted verbatim): a fenced
# code block "begins with a code fence, preceded by up to three spaces of
# indentation", and the spec's own example 134 states "Four spaces of
# indentation is too many". `\s*` (unbounded, and matching tabs) previously
# let a four-space-indented ``` ` ``` ` line put the scanner into fence
# mode, hiding a broken ADR link in the live prose that followed, since
# CommonMark treats that line as indented-code content, not a fence opener
# (Copilot, PR #5209 round-10 review).
FENCE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})")
# One level of balanced parentheses, so `gone(v2).md` and a title such as
# `"note (a)"` are still destinations. A second nested pair is not matched.
_DEST = r"(?:[^()\n]|\([^()\n]*\))*"
LINK = re.compile(rf"\[(?P<text>[^\[\]\n]*)\]\((?P<dest>{_DEST})\)")
UNTERMINATED = re.compile(rf"\[(?P<text>[^\[\]\n]*)\]\((?P<dest>{_DEST})$")
_LIST_ITEM = re.compile(r"^(?P<lead> *)(?P<marker>[-+*]|\d{1,9}[.)])(?P<gap>[ \t]+)(?P<rest>.*)$")
_BLOCKQUOTE_PREFIX = re.compile(r"^ {0,3}> ?")

# CommonMark reference links (spec.commonmark.org/0.31.2/#reference-link) are
# real links this scanner could not see at all: ``[ADR-005][decision]`` with a
# ``[decision]: ./ADR-006-wrong.md`` definition elsewhere in the same file
# carries a link text naming one ADR and a destination naming another, yet
# ``LINK`` matches only the inline ``[text](dest)`` form, so neither the
# unresolved target nor the number mismatch reached any rule and the whole
# syntax passed the repo-wide gate (Copilot, PR #5209 round-11 review).
#
# LINK_DEFINITION matches a link reference definition, which the spec allows up
# to three spaces of indentation exactly as it allows for a fence.
# REFERENCE_LINK matches the full (``[text][label]``) and collapsed
# (``[text][]``) forms; an empty label means the text is the label
# (spec.commonmark.org/0.31.2/#collapsed-reference-link). SHORTCUT_LINK matches
# the shortcut form (``[label]``), which the spec makes a link only when the
# bracket content is itself a defined label, so it is resolved against the
# collected definitions rather than treated as a link on sight; the negative
# lookahead keeps it off an inline link's ``(``, off a full reference's second
# bracket, and off a definition's own ``:``.
LINK_DEFINITION = re.compile(r"^ {0,3}\[(?P<label>[^\[\]\n]+)\]:\s*(?P<dest>.*)$")
REFERENCE_LINK = re.compile(r"\[(?P<text>[^\[\]\n]*)\]\[(?P<label>[^\[\]\n]*)\]")
SHORTCUT_LINK = re.compile(r"\[(?P<text>[^\[\]\n]+)\](?![\[(:])")


# RFC 3986 section 3.1's ABNF, quoted verbatim (rfc-editor.org/rfc/rfc3986#section-3.1):
#   scheme = ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )
# A colon-terminated scheme this shape, not a fixed enumeration, marks a
# destination as external: enumerating http/https/mailto/ftp missed ssh://,
# git://, and every other valid scheme, so a link like
# "ssh://host/ADR-005-x.md" reached ADR_BASENAME and was reported as a false
# "unresolved" repository-relative target instead of being recognized as
# external (Copilot, PR #5209 round-8 review).
EXTERNAL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def split_destination(raw: str) -> str:
    """Return the path part of a markdown link destination.

    Drops an optional ``"title"`` suffix, surrounding angle brackets, and any
    ``#anchor``. Returns an empty string when nothing path-like remains.

    The angle-bracket form is closed by its own ``>``, not by the end of the
    string: ``[ADR-005](<./ADR-005-x.md> "Title")`` is valid CommonMark (a
    pointy-bracket destination followed by a title), but ``dest`` here also
    carries that trailing title text, so ``dest.endswith(">")`` was false and
    the brackets were never stripped. The unstripped ``<./ADR-005-x.md>``
    then failed ``is_adr_target()``'s ``ADR_BASENAME`` match (its basename
    ends in ``>``, not ``.md``), so a broken or wrong-numbered link written
    with this legal syntax was silently treated as a non-ADR destination and
    never checked (Copilot, PR #5209 round-10 review). Finding the closing
    ``>`` explicitly, rather than requiring it to be the last character,
    fixes both the bracket-only and bracket-plus-title forms.
    """
    return split_destination_fragment(raw)[0]


def split_destination_fragment(raw: str) -> tuple[str, str]:
    """Return ``(path, fragment)`` for a markdown link destination.

    Same destination parsing as :func:`split_destination` (angle brackets,
    optional title), but keeps the text after the first ``#`` instead of
    dropping it. The fragment is returned without its ``#`` and is empty when
    the destination has none.
    """
    dest = raw.strip()
    if dest.startswith("<"):
        end = dest.find(">")
        if end != -1:
            # Spaces inside `<...>` are part of the path. Splitting here turned
            # `<my file.md>` into `my`.
            path, _, fragment = dest[1:end].strip().partition("#")
            return path, fragment
    if not dest:
        return "", ""
    path, _, fragment = dest.split()[0].partition("#")
    return path, fragment


def normalize_label(label: str) -> str:
    """Return a CommonMark-normalized link label.

    The spec's normalization rule, quoted verbatim
    (spec.commonmark.org/0.31.2/#matches): "To normalize a label, strip off
    the opening and closing brackets, perform the Unicode case fold, strip
    leading and trailing spaces, tabs, and line endings, and collapse
    consecutive internal spaces, tabs, and line endings to a single space."
    ``str.split()`` with no argument does the strip-and-collapse half over
    exactly that whitespace set, and ``str.casefold()`` is Python's Unicode
    case fold, so ``[Decision]`` and ``[  decision ]`` resolve to the one
    definition a Markdown renderer would give them.
    """
    return " ".join(label.split()).casefold()


def _link_definitions(lines: list[tuple[int, str]]) -> dict[str, str]:
    """Return the file's link reference definitions, normalized label to destination.

    Collected over the whole file before any line is scanned, because
    CommonMark places no ordering constraint between a reference and its
    definition: ``[ADR-005][decision]`` on line 3 is a link to whatever
    ``[decision]:`` names on line 300.

    ``setdefault`` keeps the first definition of a reused label, per the
    spec (spec.commonmark.org/0.31.2/#link-reference-definition, quoted
    verbatim): "If there are several matching definitions, the first one
    takes precedence."

    A label that normalizes to nothing is not a label, per the spec
    (spec.commonmark.org/0.31.2/#link-label, quoted verbatim): "A link label
    must contain at least one character that is not a space, tab, or line
    ending." Dropping it here is the only place that needs to know: an
    empty-normalizing label can then never be a key, so a task-list checkbox
    (``- [ ] item``) looks up nothing and a second guard at the lookup would
    be unreachable noise.
    """
    definitions: dict[str, str] = {}
    for _, line in lines:
        match = LINK_DEFINITION.match(line)
        if not match:
            continue
        label = normalize_label(match.group("label"))
        if label:
            definitions.setdefault(label, match.group("dest"))
    return definitions


def _reference_link_pairs(line: str) -> list[tuple[str, str]]:
    """Return ``(link text, label)`` for every reference-style link on one line.

    Covers the three reference forms CommonMark defines: full
    (``[text][label]``), collapsed (``[text][]``, where the text is the
    label), and shortcut (``[label]``). A shortcut match that falls inside a
    full reference's span is that reference's second bracket, not a link of
    its own, so it is dropped; ``SHORTCUT_LINK``'s lookahead already keeps
    the first bracket of a full reference and of an inline link out.

    Whether a pair is actually a link is decided by the caller, against the
    file's definitions: an undefined label renders as literal text, not a
    link, so it must not produce a finding.
    """
    pairs: list[tuple[str, str]] = []
    spans: list[tuple[int, int]] = []
    for match in REFERENCE_LINK.finditer(line):
        text = match.group("text")
        pairs.append((text, match.group("label") or text))
        spans.append(match.span())
    for match in SHORTCUT_LINK.finditer(line):
        if any(start <= match.start() < end for start, end in spans):
            continue
        pairs.append((match.group("text"), match.group("text")))
    return pairs


def _list_content_column(line: str, base: int) -> int | None:
    """Return the content column of a list item, or None.

    ``base`` is the parent item's content column, or 0 at the root. CommonMark
    allows the marker up to three spaces past that column. A gap of one to four
    spaces puts the content at the first text column. A wider gap is indented
    code, and the content column stays one space after the marker.
    """
    match = _LIST_ITEM.match(line)
    if match is None:
        return None
    lead = len(match.group("lead"))
    if lead < base or lead > base + 3:
        return None
    marker = match.group("marker")
    gap = match.group("gap").expandtabs(4)
    if match.group("rest").strip() and len(gap) <= 4:
        return lead + len(marker) + len(gap)
    return lead + len(marker) + 1


def _strip_blockquotes(line: str) -> str:
    """Drop leading blockquote markers. The returned text keeps its own indent."""
    rest = line
    while True:
        match = _BLOCKQUOTE_PREFIX.match(rest)
        if match is None:
            return rest
        rest = rest[match.end() :]


def _fence_at_column(line: str, column: int) -> tuple[str, int, bool] | None:
    """Return a fence whose marker begins at ``column``.

    ``1. ```md`` puts the opener on the marker line. ``_fence_run`` misses it
    because the columns before the backticks are ``1. ``, not whitespace. The
    indented closer is then read as a new opener and later live links disappear.
    """
    if column < 0 or column >= len(line):
        return None
    match = re.match(r"(?P<marker>`{3,}|~{3,})", line[column:])
    if match is None:
        return None
    run = match.group("marker")
    trailing = line[column + match.end() :]
    return run[0], len(run), not trailing.strip()


def _fence_run(line: str, base: int) -> tuple[str, int, bool] | None:
    """Return ``(char, length, trailing_is_blank)`` for a fence at ``base``.

    The marker may sit up to three spaces past ``base``. A four-space marker at
    the root is indented code, not a fence. A fence inside a list is judged
    from that item's content column, and a fence inside a blockquote is judged
    after the ``>`` markers are removed.
    """
    candidates = [line]
    quoted = _strip_blockquotes(line)
    if quoted != line and base == 0:
        candidates.append(quoted)
    for candidate in candidates:
        if base > len(candidate) or candidate[:base].strip():
            continue
        indent = len(candidate) - len(candidate.lstrip(" "))
        if indent < base or indent > base + 3:
            continue
        match = FENCE.match(candidate[base:])
        if match is None:
            continue
        run = match.group("marker")
        trailing = candidate[base + match.end() :]
        return run[0], len(run), not trailing.strip()
    return None


def _live_lines(body: str) -> list[tuple[int, str]]:
    """Return ``(line number, text)`` for every line outside a fenced code block.

    Fence tracking keys on the opening marker's character AND run length, not
    a bare open/closed toggle. CommonMark closes a fence only with the same
    character it opened with, in a run at least as long as the opening one
    (spec.commonmark.org section 4.5): a ```` ```` ```` (four-backtick) block
    containing a three-backtick line (a shell transcript showing a ` ``` `
    example, say) is not closed by that shorter run, and a bare open/closed
    toggle would resume scanning that fenced example content as live prose one
    fence early, or the reverse for a ``~~~`` block containing a backtick
    example. ``FENCE`` captures the whole run (``` `{3,}` ``` or ``~{3,}``),
    and a fence-shaped line closes the block only when all three hold: its
    character matches the opener's, its length matches or exceeds the
    opener's, and the rest of the line is whitespace-only, per CommonMark's
    closing-fence rule (spec.commonmark.org/0.31.2/#fenced-code-blocks). The
    third condition is why a line such as ``` ```python ``` inside an
    already-open ``` block is content (an inner example) rather than a close:
    a closing fence takes no info string (Copilot, PR #5209 round-9 review).
    Any other fence-shaped line while inside a fence is likewise content, not
    a delimiter. (Round 7 corrected an earlier version of this docstring
    which said the length condition was deferred because "no fence in this
    corpus nests same-character runs of different lengths" -- true of the
    corpus at the time, not a property the scanner can rely on going
    forward.) A fence indented to a list item's content column, or written
    after blockquote markers, is a fence. A four-space marker at the root is
    still indented code, not a fence. Inline single-backtick spans are masked
    separately by :func:`mask_inline_code`.

    Returning the surviving lines, rather than scanning them in place, is
    what lets ``scan_file`` collect the file's link reference definitions
    before it scans any line: a reference may precede its definition, and a
    definition inside a fence is an illustration, not a definition.
    """
    live: list[tuple[int, str]] = []
    fence_char: str | None = None
    fence_length = 0
    fence_base = 0
    list_columns: list[int] = []
    for line_number, line in enumerate(body.splitlines(), 1):
        item_column: int | None = None
        if fence_char is None:
            indent = len(line) - len(line.lstrip(" "))
            while list_columns and line.strip() and indent < list_columns[-1]:
                list_columns.pop()
            item_column = _list_content_column(line, list_columns[-1] if list_columns else 0)
            if item_column is not None:
                list_columns.append(item_column)
            base = list_columns[-1] if list_columns else 0
        else:
            base = fence_base
        found = _fence_run(line, base)
        if found is None and item_column is not None:
            found = _fence_at_column(line, item_column)
        if found:
            char, length, trailing_is_whitespace_only = found
            # A closing fence may be followed only by spaces or tabs, per
            # CommonMark (spec.commonmark.org/0.31.2/#fenced-code-blocks,
            # quoted verbatim): "The closing code fence may be preceded by
            # up to three spaces of indentation, and may be followed only by
            # spaces or tabs, which are ignored." An opening fence has no
            # such restriction; its info string can carry any text (a
            # language tag, a shell prompt). Before this fix, a line like
            # "```python" inside an already-open ``` block matched the same
            # char/length as the opener and closed it, so the block's real
            # closing fence was then read as a new opener: a nested example
            # in the fenced content could report links, and a broken link in
            # the live prose that followed could be silently skipped
            # (Copilot, PR #5209 round-9 review).
            if fence_char is None:
                fence_char, fence_length, fence_base = char, length, base
            elif char == fence_char and length >= fence_length and trailing_is_whitespace_only:
                fence_char, fence_length, fence_base = None, 0, 0
            # else: a fence-shaped line that does not close (wrong character,
            # a shorter run than the opener, or trailing text after the
            # marker) is content, not a delimiter; fence_char/fence_length hold.
            continue
        if fence_char is None:
            live.append((line_number, line))

    return live


_INLINE_CODE_SPAN = re.compile(r"(?P<ticks>`+)(?:(?!(?P=ticks)).)+?(?P=ticks)")


def mask_inline_code(line: str, *, links_only: bool = True) -> str:
    """Blank inline code spans on one line, keeping every column.

    A ``[x](y.md)`` shown inside backticks is an example, not a link. With
    ``links_only``, a code span that does not itself contain a bracket stays,
    so a shortcut label such as ``[`foo`]`` still resolves. Anchor scanning
    passes ``links_only=False`` so an example ``<a id>`` is not a real anchor.
    A span that wraps across lines is not masked; this is a line scanner.
    """

    def blank(match: re.Match[str]) -> str:
        span = match.group(0)
        if links_only and "[" not in span and "]" not in span:
            return span
        return " " * len(span)

    return _INLINE_CODE_SPAN.sub(blank, line)
