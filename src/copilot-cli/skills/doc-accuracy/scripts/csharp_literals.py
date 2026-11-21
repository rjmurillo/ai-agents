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


def _csharp_string_end(code: str, body: int, prefix: str, chars: list[str]) -> tuple[int, bool]:
    """Blank a regular or verbatim string body; return (end, closed).

    ``closed`` is true only when the string ended at its closing quote.

    Interpolation holes stay visible because they hold code. A regular string
    ends at an unescaped quote. One that reaches its line end instead was
    never closed, so its quote is a typo: the body is restored and stays
    visible, which can over-report a name but never hide one. An
    unterminated verbatim string, or one whose hole never closes, is
    restored the same way. A multi-line verbatim close that may be borrowed
    from a later literal is settled by ``_union_verbatim_readings``.
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
                if verbatim:
                    chars[body:index] = code[body:index]
                return index, False
            continue
        if char == '"' and not (verbatim and code.startswith('""', index)):
            if verbatim and _distrusts_verbatim_close(code, body, index):
                return _union_verbatim_readings(code, body, index, chars), True
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


def _union_verbatim_readings(code: str, body: int, close: int, chars: list[str]) -> int:
    """Settle a doubtful multi-line verbatim close; return where to resume.

    Two readings cover the text from the body to the end of the close's
    line. In one, the close is real: the body is literal text and the rest
    of that line is code. In the other, the opening quote was a typo: the
    whole span is code. A character stays visible when either reading shows
    it, so a name is hidden only when both readings hide it. One reading is
    the true one, so this can over-report but never hides real code.
    """
    stop = line_end(code, close)
    as_closed = chars[body : close + 1] + list(_lex_span(code, close + 1, stop))
    as_code = _lex_span(code, body, stop)
    for offset, (closed_char, code_char) in enumerate(zip(as_closed, as_code, strict=True)):
        original = code[body + offset]
        chars[body + offset] = original if original in (closed_char, code_char) else " "
    return stop


def _lex_span(code: str, start: int, end: int) -> str:
    """Blank literals in code[start:end] read alone; unreadable spans stay visible."""
    span = code[start:end]
    blanked = blank_csharp_literals(span)
    return span if blanked is None else blanked


def _distrusts_verbatim_close(code: str, body: int, close: int) -> bool:
    """Whether a verbatim string's closing quote on a later line may be borrowed.

    A missing close quote makes a multi-line verbatim string borrow a later
    literal's quote. A borrowed quote is followed by name text (other than a
    ``u8`` suffix), or it opens a literal: it is a lone quote or a raw
    opener after an operator, a bracket, a separator, or a keyword such as
    ``return``. A doubtful close is settled by reading the span both ways,
    so a false alarm only over-reports.
    """
    if code.find("\n", body, close) < 0:
        return False
    rest = code[close + 1 : line_end(code, close)]
    if rest[:1].isalnum() or rest[:1] == "_":
        return not (rest[:2] == "u8" and not rest[2:3].isalnum())
    if code[close - 1 : close] == "'" and rest[:1] == "'":
        return True  # the quote is a char literal such as '"'
    run_start = close
    while run_start > body and code[run_start - 1] == '"':
        run_start -= 1
    raw_opener = close - run_start >= 2 and not rest.strip()
    if close != run_start and not raw_opener:
        return False
    prefix = code[code.rfind("\n", 0, run_start) + 1 : run_start].rstrip()
    last_word = re.search(r"[A-Za-z_]\w*$", prefix)
    if last_word is not None:
        return last_word.group(0) in _LITERAL_KEYWORDS
    return bool(prefix) and prefix[-1] in _LITERAL_OPENER_CHARS


# Characters and keywords that end the text right before a literal opens.
_LITERAL_OPENER_CHARS = frozenset("=([{)]},:?+-*/%<>!&|^~;$@")
_LITERAL_KEYWORDS = frozenset(
    {"return", "case", "yield", "in", "is", "when", "and", "or", "not", "throw", "await"}
)


def _csharp_raw_string_end(code: str, match: re.Match[str], chars: list[str]) -> tuple[int, bool]:
    """Blank a raw string body; return (end, closed) for its closing quotes.

    A raw string closes on the same quote run that opened it. With N "$"
    markers, a run of N braces opens a hole, which stays visible; braces
    before it in a longer run are literal text. An unterminated raw string,
    or one whose hole never closes, is left visible, so no code is hidden.
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
        index, closed = csharp_hole_end(code, hole, chars, quotes, _skip_csharp_token)
        if not closed:
            # A broken hole means the raw string cannot be read reliably, so
            # its whole text stays visible up to its close or line end.
            close = _csharp_raw_close(code, quotes, match.end(), index)
            end = line_end(code, index) if close < 0 else close + len(quotes)
            chars[match.end() : end] = code[match.end() : end]
            return end, close >= 0


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
