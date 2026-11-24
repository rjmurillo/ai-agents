"""Blank C# string and char literal text, keeping every column.

The doc-accuracy scanner uses this before it looks for C# identifiers, so a
name that appears only inside a literal is not reported as an unresolved
symbol. ``csharp_holes.py`` scans interpolation holes, and its
``blank_csharp_attribute_named_args`` then blanks attribute named arguments.

Every function works on ``chars``, a list copy of the snippet with one
entry per character, so columns and newlines never move. Rule for that
buffer: a scanner blanks a span when it is sure the span is literal text.
When a string never closes, the whole snippet is left unblanked, because
hiding real code is worse than reporting a literal word.

Standard library only: the doc-accuracy skill runs on the host's Python.
"""

from __future__ import annotations

import re

from csharp_holes import CSHARP_TOKEN_START_RE, blank_span, csharp_hole_end, line_end

__all__ = ["blank_csharp_literals"]


# A C# char literal holds one character or one escape sequence.
_CHAR_LITERAL_RE = re.compile(
    r"'(?:[^'\\\n]|\\(?:['\"\\0abefnrtv]|x[0-9A-Fa-f]{1,4}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}))'"
)


def _csharp_char_end(code: str, start: int) -> int:
    """Index past the char literal opened at ``start``, or just past ``start``.

    Anything that is not exactly one character or one escape between the
    apostrophes is a typo or prose, so the scan resumes right after the
    apostrophe and pairs it with nothing.
    """
    literal = _CHAR_LITERAL_RE.match(code, start)
    return literal.end() if literal else start + 1


class _MultilineVerbatimError(Exception):
    """A verbatim string's text reached a newline, so the snippet is unread."""


def _csharp_string_end(code: str, body: int, prefix: str, chars: list[str]) -> tuple[int, bool]:
    """Blank a regular or verbatim string body; return (end, closed).

    ``closed`` is true only when the string ended at its closing quote.

    Interpolation holes stay visible because they hold code. A regular string
    ends at an unescaped quote; one that reaches its line end, or whose hole
    never closes, is not closed. A verbatim string whose text reaches a
    newline raises ``_MultilineVerbatimError``: its close may be a later
    literal's quote, borrowed because its own close is missing, and no local
    rule tells the two apart. Either way ``blank_csharp_literals`` leaves the
    whole snippet unblanked.
    """
    verbatim, interpolated = "@" in prefix, "$" in prefix
    index = body
    while index < len(code):
        char = code[index]
        if interpolated and char == "{" and not code.startswith("{{", index):
            index, closed = csharp_hole_end(
                code, index, chars, '"' if verbatim else "\\", _skip_csharp_token
            )
            if not closed:
                return index, False
            continue
        if char == '"' and not (verbatim and code.startswith('""', index)):
            return index + 1, True
        if char == "\n":
            if verbatim:
                raise _MultilineVerbatimError
            return index, False
        escaped = char == "\\" and not verbatim and code[index + 1 : index + 2] not in ("", "\n")
        doubled = code.startswith(char * 2, index) and char in '{"'
        step = 2 if escaped or doubled else 1
        blank_span(chars, index, index + step)
        index += step
    return index, False


def _csharp_raw_string_end(code: str, match: re.Match[str], chars: list[str]) -> tuple[int, bool]:
    """Blank a raw string body; return (end, closed) for its closing quotes.

    A raw string closes on the same quote run that opened it. With N "$"
    markers, a run of N braces opens a hole, which stays visible; braces
    before it in a longer run are literal text. An unterminated raw string,
    one whose hole never closes, or one whose hole runs past the closing
    run is not closed. The close is found once, so the scan stays linear.
    """
    quotes, dollars = match.group("quotes"), match.group("prefix").count("$")
    index = match.end()
    close = _csharp_raw_close(code, quotes, index, index)
    while True:
        if close < 0:
            return line_end(code, index), False
        if index > close:
            return index, False
        hole = code.find("{" * dollars, index, close) if dollars else -1
        if hole < 0:
            blank_span(chars, index, close)
            return close + len(quotes), True
        while code.startswith("{" * (dollars + 1), hole):
            hole += 1
        blank_span(chars, index, hole)
        index, closed = csharp_hole_end(code, hole, chars, quotes, _skip_csharp_token)
        if not closed:
            return index, False


def _csharp_raw_close(code: str, quotes: str, body: int, index: int) -> int:
    """Index of the raw string's closing run at or after ``index``, or -1.

    Follows the C# raw string rules. Text after the opening run makes it a
    single-line string that must close on that line. Otherwise content can
    never hold a run as long as the delimiter, so the first such run must
    be the close: alone on its line after only whitespace, with every
    content line starting with that whitespace. Any other first run means
    the close is missing, so a later string's quotes are never borrowed.
    """
    opening_line_end = line_end(code, body)
    if code[body:opening_line_end].strip():
        return code.find(quotes, index, opening_line_end)
    pos = code.find(quotes, max(index, opening_line_end))
    if pos < 0:
        return -1
    line_start = code.rfind("\n", 0, pos) + 1
    indent = code[line_start:pos]
    if indent.strip() or not _raw_lines_indented(code, opening_line_end + 1, line_start, indent):
        return -1
    return pos


def _raw_lines_indented(code: str, start: int, end: int, indent: str) -> bool:
    """Whether every non-blank line in code[start:end] starts with ``indent``."""
    return all(line.startswith(indent) or not line.strip() for line in code[start:end].split("\n"))


def _blank_csharp_string(code: str, match: re.Match[str], chars: list[str]) -> tuple[int, bool]:
    """Blank the string literal ``match`` opens; return (end, closed)."""
    prefix, quotes = match.group("prefix"), match.group("quotes")
    if "@" not in prefix and len(quotes) >= 3:
        return _csharp_raw_string_end(code, match, chars)
    if "@" not in prefix and len(quotes) == 2:
        return match.end(), True
    return _csharp_string_end(code, match.start("quotes") + 1, prefix, chars)


def _blank_csharp_literal(code: str, match: re.Match[str], chars: list[str]) -> tuple[int, bool]:
    """Blank the string or char literal ``match`` opens; return (end, closed)."""
    if match.group(0) != "'":
        return _blank_csharp_string(code, match, chars)
    end = _csharp_char_end(code, match.start())
    closed = end - 1 > match.start()
    if closed:
        blank_span(chars, match.start() + 1, end - 1)
    return end, closed


def _skip_csharp_token(code: str, match: re.Match[str], chars: list[str]) -> tuple[int, bool]:
    """Pass the comment or literal ``match`` opens; return (end, closed).

    A comment is left unchanged. A literal is blanked. ``closed`` is false
    for a literal without its closing quote or a block comment without
    "*/".
    """
    if match.group(0) == "//":
        return line_end(code, match.end()), True
    if match.group(0) == "/*":
        end = code.find("*/", match.end())
        return (len(code), False) if end < 0 else (end + 2, True)
    return _blank_csharp_literal(code, match, chars)


def blank_csharp_literals(code: str) -> str | None:
    """Blank C# string and char literal text, keeping every column.

    Covers regular, verbatim (@), interpolated ($, $@, @$) and raw (three or
    more quotes, with any $ markers) strings, plus char literals. Holes stay
    visible, and literals nested in a hole are blanked too. Comments are
    skipped unchanged, so a quote inside one opens nothing.

    Returns None when the snippet cannot be read safely: a string that never
    closes, a verbatim string whose text spans a line break, or hole nesting
    past the recursion limit (only hundreds of nested $"{ levels reach it).
    Guessing where a broken literal ends can hide real code, so the caller
    scans the raw code instead, which can over-report a literal word but
    never hides code. A char literal or block comment that never closes
    blanks nothing, so the scan goes on past it.
    """
    chars = list(code)
    index = 0
    try:
        while (match := CSHARP_TOKEN_START_RE.search(code, index)) is not None:
            index, closed = _skip_csharp_token(code, match, chars)
            if not closed and match.group("quotes"):
                return None
    except (RecursionError, _MultilineVerbatimError):
        return None
    return "".join(chars)
