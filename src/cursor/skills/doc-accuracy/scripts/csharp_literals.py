"""Blank C# string and char literal text, keeping every column.

The doc-accuracy scanner uses this before it looks for C# identifiers, so a
name that appears only inside a literal is not reported as an unresolved
symbol. ``csharp_holes.py`` scans interpolation holes, and
``csharp_attributes.py`` then blanks attribute named arguments.

Every function works on ``chars``, a list copy of the snippet with one
entry per character, so columns and newlines never move. Rule for that
buffer: a scanner blanks a span when it is sure the span is literal text.
When a later check finds the literal or hole was never closed, it restores
the span from ``code``. A restore always wins, because hiding real code is
worse than reporting a literal word.

Standard library only: the doc-accuracy skill runs on the host's Python.
"""

from __future__ import annotations

import re

from csharp_holes import CSHARP_TOKEN_START_RE, blank_span, csharp_hole_end, line_end

__all__ = ["blank_csharp_literals"]


# The longest valid char literal body is a \U escape: ten characters.
_MAX_CHAR_LITERAL_BODY = 10


def _csharp_char_end(code: str, start: int) -> int:
    """Index past the char literal opened at ``start``, or just past ``start``.

    A literal must close within ``_MAX_CHAR_LITERAL_BODY`` characters on its
    line. Otherwise the apostrophe is a typo or prose, so the scan resumes
    right after it and pairs it with nothing.
    """
    limit = min(len(code), start + 2 + _MAX_CHAR_LITERAL_BODY)
    index = start + 1
    while index < limit and code[index] != "\n":
        if code[index] == "\\" and code[index + 1 : index + 2] not in ("", "\n"):
            index += 2
            continue
        if code[index] == "'":
            return index + 1
        index += 1
    return start + 1


def _csharp_string_end(code: str, body: int, prefix: str, chars: list[str]) -> tuple[int, bool]:
    """Blank a regular or verbatim string body; return (end, closed).

    ``closed`` is true only when the string ended at its closing quote.

    Interpolation holes stay visible because they hold code. A regular string
    ends at an unescaped quote. One that reaches its line end instead was
    never closed, so its quote is a typo: the body is restored and stays
    visible, which can over-report a name but never hide one. An
    unterminated verbatim string is restored the same way, and the scan
    resumes at its opening line end.
    """
    verbatim, interpolated = "@" in prefix, "$" in prefix
    index = body
    while index < len(code):
        char = code[index]
        if interpolated and char == "{" and not code.startswith("{{", index):
            if verbatim and _in_code_context(code, body, index):
                chars[body:index] = code[body:index]
                return line_end(code, body), False
            index, closed = csharp_hole_end(
                code, index, chars, '"' if verbatim else "\\", _skip_csharp_token
            )
            if not closed:
                return index, False
            continue
        if char == '"' and not (verbatim and code.startswith('""', index)):
            if verbatim and _distrusts_verbatim_close(code, body, index):
                chars[body:index] = code[body:index]
                return line_end(code, body), False
            return index + 1, True
        if char == "\n" and not verbatim:
            chars[body:index] = code[body:index]
            return index, False
        escaped = char == "\\" and not verbatim and code[index + 1 : index + 2] not in ("", "\n")
        doubled = code.startswith(char * 2, index) and char in '{"'
        step = 2 if escaped or doubled else 1
        blank_span(chars, index, index + step)
        index += step
    chars[body:index] = code[body:index]
    if verbatim:
        return line_end(code, body), False
    return index, False


def _distrusts_verbatim_close(code: str, body: int, close: int) -> bool:
    """Whether a verbatim string's closing quote on a later line is a pairing.

    A multi-line verbatim string is valid C#, but a missing close quote
    makes the string borrow a later literal's quote. That borrowed quote is
    followed by more name text or by another quote on its line, which a
    real close rarely is, or it sits right after text that opens a literal,
    such as "= " or a "$" prefix, or inside a char literal or comment on its
    line. Distrusting it can over-report, never hide.
    """
    if code.find("\n", body, close) < 0:
        return False
    following = code[close + 1 : close + 2]
    if following.isalnum() or following == "_" or '"' in code[close + 1 : line_end(code, close)]:
        return True
    run_start = close
    while run_start > body and code[run_start - 1] == '"':
        run_start -= 1
    line_start = code.rfind("\n", 0, run_start) + 1
    prefix = code[line_start:run_start]
    return _in_code_context(code, body, run_start) or prefix.rstrip().endswith(_LITERAL_OPENERS)


def _in_code_context(code: str, body: int, index: int) -> bool:
    """Whether ``index``, on a later line of a verbatim string, looks like code.

    It does when it sits right after an apostrophe (a char literal) or after
    a "//" or "/*" on its line (a comment). A verbatim string that runs on
    to such a spot has lost its closing quote.
    """
    if code.find("\n", body, index) < 0:
        return False
    prefix = code[code.rfind("\n", 0, index) + 1 : index]
    return prefix.endswith("'") or "//" in prefix or "/*" in prefix


# Text that ends right before a literal opens: an assignment, an argument,
# an interpolation or verbatim prefix, or an initializer.
_LITERAL_OPENERS = ("=", "(", ",", "$", "@", "[", "{", ":", "?", "return")


def _csharp_raw_string_end(code: str, match: re.Match[str], chars: list[str]) -> tuple[int, bool]:
    """Blank a raw string body; return (end, closed) for its closing quotes.

    A raw string closes on the same quote run that opened it. With N "$"
    markers, a run of N braces opens a hole, which stays visible; braces
    before it in a longer run are literal text. An unterminated raw string
    is left visible, so no code after it is hidden.
    """
    quotes, dollars = match.group("quotes"), match.group("prefix").count("$")
    index, close = match.end(), -1
    while True:
        if close < index:
            close = _csharp_raw_close(code, quotes, match.end(), index)
        if close < 0:
            # No valid closing run: the opening quotes are a typo, so the
            # text stays visible. That can over-report but never hides code.
            end = line_end(code, index)
            chars[match.end() : end] = code[match.end() : end]
            return end, False
        hole = code.find("{" * dollars, index, close) if dollars else -1
        if hole < 0:
            blank_span(chars, index, close)
            return close + len(quotes), True
        while code.startswith("{" * (dollars + 1), hole):
            hole += 1
        blank_span(chars, index, hole)
        index, _ = csharp_hole_end(code, hole, chars, quotes, _skip_csharp_token)


def _csharp_raw_close(code: str, quotes: str, body: int, index: int) -> int:
    """Index of the raw string's closing run at or after ``index``, or -1.

    Follows the C# raw string rules. Text after the opening run makes it a
    single-line string that must close on that line. Otherwise the close
    must sit on its own line after only whitespace, and every content line
    must start with that same whitespace. A run that breaks these rules is
    not a close, so a missing close cannot borrow a later string's quotes.
    """
    opening_line_end = line_end(code, body)
    if code[body:opening_line_end].strip():
        return code.find(quotes, index, opening_line_end)
    pos = code.find(quotes, max(index, opening_line_end))
    while pos >= 0:
        line_start = code.rfind("\n", 0, pos) + 1
        indent = code[line_start:pos]
        if not indent.strip():
            return (
                pos if _raw_lines_indented(code, opening_line_end + 1, line_start, indent) else -1
            )
        pos = code.find(quotes, line_end(code, pos))
    return -1


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

    Returns None when hole nesting exceeds the recursion limit. Holes nest by
    recursion, and only hundreds of nested $"{ levels reach the limit, which
    no real snippet does.
    """
    chars = list(code)
    index = 0
    try:
        while (match := CSHARP_TOKEN_START_RE.search(code, index)) is not None:
            index, _ = _skip_csharp_token(code, match, chars)
    except RecursionError:
        return None
    return "".join(chars)
