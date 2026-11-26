"""CommonMark link reference definition grammar, shared by two skill scripts.

`fix-markdown-fences` and `prose-self-check` both need to know when a line is
a link reference definition, because a definition changes what CommonMark reads
as a paragraph and so where a fence can open. One copy lives here so a defect
fixed once is fixed for both (issue #5352).

The module is import-self-contained: it uses only the standard library, so the
lib mirror can copy it unchanged into each plugin tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A link reference definition, validated rather than sniffed. An earlier
# version required only `\\S` after the colon, which accepted `[foo]: <broken`
# and `[foo]: /url "unclosed`. CommonMark reads both as paragraph text, so
# clearing paragraph state there let `--write` append a fence to a document
# holding no fence at all. Measured against the reference parser over 22
# destination and title shapes; these three patterns agree with it on all 22.
#
# The title is a quoted or parenthesised run. Each form may carry a
# backslash-escaped copy of its own delimiter, which is why every alternative
# spells the escape: `[^"]*` stopped at the backslash in `"a\\"b"` and read a
# valid title as prose. CommonMark forbids an UNESCAPED parenthesis inside the
# parenthesised form, so one level is the whole grammar there and a pattern
# can spell it; the destination cannot say the same, hence the scanner below.
_LINK_TITLE = r"(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|\((?:[^()\\]|\\.)*\))"
# `\s`, not `[ \t]`. CommonMark normalises a label before comparing it, so a
# label holding only whitespace normalises to empty and the line is not a
# definition. The guard tested space and tab alone, so `[\xa0]: /url` parsed
# here as a definition, cleared paragraph state the reference parser keeps,
# and `--write` appended a fence to a document holding none.
_LINK_LABEL = r"\[(?!\s*\])(?:[^\[\]\\]|\\.)*\]"
LINK_TITLE_ONLY = re.compile(rf"^{_LINK_TITLE}[ \t]*$")
# CommonMark also lets the destination start on the line AFTER the label. The
# label line stays paragraph text until a valid destination proves otherwise,
# which is why `_awaiting_link_destination` defers rather than deciding: with
# `[foo]:` followed directly by `2.`, the reference parser keeps the paragraph
# and vetoes the marker, and deciding early would break that.
LINK_LABEL_ONLY = re.compile(rf"^{_LINK_LABEL}:[ \t]*$")
_LINK_LABEL_COLON = re.compile(rf"^{_LINK_LABEL}:[ \t]*")


def _angle_destination_end(body: str, start: int) -> int | None:
    """Return the index just past the `<...>` destination at *start*, or None.

    Character by character, not `find(">")`. CommonMark lets the angle form
    carry an ESCAPED copy of either delimiter, so `find` stopped at the `\\>`
    in `<foo\\>bar>` and a substring test rejected the `\\<` in `<foo\\<bar>`.
    Both are valid definitions, both were read as prose, and `--write` then
    appended a fence to a balanced document.
    """
    index = start + 1
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            index += 2
            continue
        if char == "<":
            return None  # an UNESCAPED `<` may not appear inside
        if char == ">":
            return index + 1
        index += 1
    return None  # the angle form never closed


def _link_destination_end(body: str, start: int) -> int | None:
    """Return the index just past the link destination at *start*, or None.

    The bracketless destination form allows parentheses at ANY nesting depth
    so long as they balance. A regex alternative can only spell a fixed depth,
    and the one that shipped spelled a single level, so `[foo]: /u(r(l))` was
    read as prose here and as a definition by the reference parser. That kept
    a paragraph open, vetoed the following list marker, and let `--write`
    append a fence to a balanced document. A scanner has no depth ceiling to
    get wrong; the reference parser accepts four levels and offers no reason
    to believe it stops there.

    The angle form is delegated but tested first, because a bare run must not
    begin with `<`: letting it swallow `<broken` is the defect this grammar
    exists to prevent.
    """
    if start < len(body) and body[start] == "<":
        return _angle_destination_end(body, start)
    index, depth = start, 0
    while index < len(body):
        char = body[index]
        if char in " \t":
            break
        if char == "\\" and index + 1 < len(body):
            index += 2  # an escaped character never counts as a delimiter
            continue
        if "\x01" <= char <= "\x1f" or char == "\x7f":
            # A bare destination may not carry an ASCII control character.
            # Measured over the whole range: the reference parser rejects
            # every one of U+0001 to U+0020 and U+007F, and accepts only
            # U+0000, which it replaces with U+FFFD before parsing. Space and
            # tab are already the break above, so this covers the other 29.
            # We accepted all of them and so read a definition where the
            # reference parser reads a paragraph, which made the scanner MISS
            # a genuinely unclosed fence rather than invent one.
            return None
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return None  # a closer with no opener
        index += 1
    if depth != 0 or index == start:
        return None  # unbalanced, or no destination at all
    return index


_TITLE_CLOSERS = {'"': '"', "'": "'", "(": ")"}


def _title_end(body: str, start: int) -> int | str | None:
    """Return the index past a title at *start*, the delimiter it awaits, or None.

    A CommonMark title may run across lines until its closing delimiter, so a
    title that opens here and does not close is not a failure: it is a state.
    A string result IS that state, the delimiter still expected; an int is a
    title complete on this line. Callers distinguish them with `isinstance`,
    because both are truthy and only one means "done".
    """
    if start >= len(body):
        return None
    closer = _TITLE_CLOSERS.get(body[start])
    if closer is None:
        return None
    index = start + 1
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            index += 2  # a delimiter may be escaped inside its own title
            continue
        if char == closer:
            return index + 1
        if closer == ")" and char == "(":
            return None  # an UNESCAPED `(` may not appear in a parenthesised title
        index += 1
    return closer


def label_opens(body: str) -> bool:
    """Return True when a link label opens in *body* and does not close on it.

    CommonMark lets a label span lines, which the single-line patterns cannot
    express: `[fo` / `o]: /url` is a definition to the reference parser and was
    prose here, so the marker below it was vetoed and `--write` appended a
    fence to a balanced document.
    """
    if not body.startswith("["):
        return False
    index = 1
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body):
            index += 2
            continue
        if char == "]":
            return False  # it closed here, so the single-line patterns own it
        if char == "[":
            return False  # an UNESCAPED `[` is not allowed inside a label
        index += 1
    return True


@dataclass(frozen=True, slots=True)
class Definition:
    """What a parsed link reference definition still expects.

    `awaiting_title` means it carries none yet, so a bare title may continue it
    on the next line. `open_title` is the delimiter a title opened on this line
    is still waiting for. Both empty means the definition is complete.
    """

    awaiting_title: bool = False
    open_title: str | None = None


def link_tail(body: str, start: int) -> Definition | None:
    """Return what the definition beginning at *start* still expects, or None.

    None means the rest of the line is not a destination optionally followed by
    one title, so the line is prose. Callers must test `is None` rather than
    truthiness, because a complete definition is a falsy-looking empty record.
    """
    end = _link_destination_end(body, start)
    if end is None:
        return None
    rest = body[end:]
    if not rest.strip(" \t"):
        return Definition(awaiting_title=True)
    separated = rest.lstrip(" \t")
    if len(separated) == len(rest):
        return None  # a title must be separated from the destination
    result = _title_end(body, end + len(rest) - len(separated))
    if result is None:
        return None
    if isinstance(result, str):
        return Definition(open_title=result)
    return None if body[result:].strip(" \t") else Definition()


def bare_title(body: str) -> bool | str | None:
    """Return True for a complete title line, the awaited delimiter, or None.

    This is the next-line form, which may itself open a multi-line title.
    """
    result = _title_end(body, 0)
    if result is None or isinstance(result, str):
        return result
    return True if not body[result:].strip(" \t") else None


def link_reference(body: str) -> Definition | None:
    """Return what a same-line definition still expects, or None for prose."""
    match = _LINK_LABEL_COLON.match(body)
    return None if match is None else link_tail(body, match.end())
