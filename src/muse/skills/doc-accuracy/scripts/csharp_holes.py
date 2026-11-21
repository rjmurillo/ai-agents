"""Scan C# interpolation holes for the doc-accuracy literal blanker.

A hole is the ``{...}`` code inside an interpolated string. It stays
visible, but literals inside it are blanked and a format specifier such as
``:N2`` is blanked as literal text. ``csharp_literals.py`` drives this scan
and passes in its own token skipper, so this module imports no sibling.

Standard library only: the doc-accuracy skill runs on the host's Python.
"""

from __future__ import annotations

import re
from collections.abc import Callable

__all__ = ["CSHARP_TOKEN_START_RE", "SkipToken", "blank_span", "csharp_hole_end", "line_end"]

# Passes the comment or literal a token match opens; returns (end, closed).
SkipToken = Callable[[str, "re.Match[str]", list[str]], tuple[int, bool]]


# The start of a C# comment or literal. A comment is consumed but kept, so a
# quote inside it opens nothing. "prefix" holds the $ and @ markers of a
# string. The cap keeps a long marker run from being rescanned at every start.
CSHARP_TOKEN_START_RE = re.compile(r"//|/\*|'|(?P<prefix>[$@]{0,8})(?P<quotes>\"+)")


def blank_span(chars: list[str], start: int, end: int) -> None:
    """Replace chars[start:end] with spaces, keeping newlines."""
    for index in range(start, end):
        if chars[index] != "\n":
            chars[index] = " "


def line_end(code: str, index: int) -> int:
    """Index of the newline at or after ``index``, or the end of ``code``."""
    end = code.find("\n", index)
    return len(code) if end < 0 else end


def csharp_hole_end(
    code: str, start: int, chars: list[str], escape: str, skip_token: SkipToken
) -> tuple[int, bool]:
    """Scan the hole opened at ``start``; return (end, closed).

    ``end`` is just past the hole's closing "}" when ``closed`` is true,
    else where the enclosing string must stop. ``escape`` is the enclosing
    string's kind: "\\" regular, '"' verbatim, or the raw opening run.
    ``skip_token`` passes one comment or literal and reports if it closed.

    The hole is code and stays visible. Literals inside it are blanked and
    comments skipped. A format specifier, as in ``{price:N2}``, is blanked
    once its "}" arrives; a ":" counts only before any newline, top-level
    ";", statement word, or ternary "?" ("?.", "??" and an unspaced "?[" are
    not), and a specifier meeting a newline, quote, or "{" stays visible.

    In regular and verbatim strings a hole may span ``_MAX_HOLE_LINES``
    lines. It is unclosed at that cap, at the snippet end, when a nested
    literal or comment lacks its close, or when an interpolated string
    opens on a later line. An unclosed hole is restored and the enclosing
    string stops at its opening line end. In a raw string, a quote run that
    closes nothing ends the hole there.

    Accepted limits: chained unclosed holes or literals on one line, a
    string missing its close quote that pairs with a later quote on that
    line, and a valid hole over the line cap or holding an interpolated
    string on a later line can still blank code up to the next quote.
    """
    return _HoleScan(code, chars, escape, start, skip_token).run()


# A hole spanning more lines than this is treated as unclosed. The cap keeps
# rescans linear when many unclosed holes stack on consecutive lines.
_MAX_HOLE_LINES = 16


class _HoleScan:
    """Scan state for one interpolation hole; see ``csharp_hole_end``."""

    def __init__(
        self, code: str, chars: list[str], escape: str, start: int, skip_token: SkipToken
    ) -> None:
        opening = start
        while opening < len(code) and code[opening] == "{":
            opening += 1
        self._code = code
        self._chars = chars
        self._escape = escape
        self._start = start
        self._base = opening - start
        self._depth = 0
        self._paren = 0
        self._index = start
        self._line_bound = escape in ("\\", '"')
        self._format_allowed = True
        self._closed = False
        self._lines = 0
        self._skip_token = skip_token

    def run(self) -> tuple[int, bool]:
        """Scan to the hole's end; return (end, closed) as ``csharp_hole_end``."""
        while self._index < len(self._code):
            done = self._step()
            if done is not None:
                return done, self._closed
        if self._line_bound:
            return self._unclosed(self._index), False
        return self._index, False

    def _step(self) -> int | None:
        """Advance past one token or character; return the hole end once known."""
        token = CSHARP_TOKEN_START_RE.match(self._code, self._index)
        if token is not None:
            return self._token(token)
        char = self._code[self._index]
        if char == "\n" and self._count_lines(1):
            return self._unclosed(self._index)
        top_level = self._paren == 0 and self._depth == self._base
        if char == "\n" or (top_level and _ends_format_context(self._code, self._index)):
            self._format_allowed = False
        if char in "{}":
            return self._brace(char)
        if char in "([)]":
            self._paren += 1 if char in "([" else -1
        elif self._code.startswith("::", self._index):
            self._index += 1
        elif char == ":" and top_level and self._format_allowed:
            self._format_span()
            return None
        self._index += 1
        return None

    def _token(self, token: re.Match[str]) -> int | None:
        code, index = self._code, self._index
        if self._line_bound and self._lines and "$" in (token.group("prefix") or ""):
            # An interpolated string opening on a later line of this hole
            # would nest one hole per line. Treat this hole as broken here.
            return self._unclosed(index, resume=index)
        after, closed = self._skip_token(code, token, self._chars)
        if _closes_outer_raw_string(code, token, after, self._escape):
            self._chars[index:after] = code[index:after]
            return index
        if self._line_bound and not closed:
            # A nested literal or comment with no close means this hole is
            # broken: its quote was the outer close, or an inner hole never
            # closed. Resume at that token so it is scanned once, at top level.
            return self._unclosed(after, resume=index)
        newlines = code.count("\n", index, after)
        if newlines:
            self._format_allowed = False
            if self._count_lines(newlines):
                return self._unclosed(after, resume=index)
        self._index = after
        return None

    def _count_lines(self, newlines: int) -> bool:
        """Record crossed newlines; return whether the hole is over the cap."""
        self._lines += newlines
        return self._line_bound and self._lines > _MAX_HOLE_LINES

    def _brace(self, char: str) -> int | None:
        self._depth += 1 if char == "{" else -1
        self._index += 1
        if self._depth != 0:
            return None
        self._closed = True
        return self._index

    def _format_span(self) -> None:
        self._format_allowed = False
        stop = _csharp_format_span_end(self._code, self._index + 1, self._escape)
        if self._code.startswith("}" * self._base, stop):
            blank_span(self._chars, self._index + 1, stop)
        self._index = stop

    def _unclosed(self, end: int, resume: int | None = None) -> int:
        """Undo blanking up to ``end``; return where the enclosing string stops.

        That is the hole's opening line end, or ``resume`` when earlier: the
        start of a token that broke the hole, so it is rescanned only once.
        """
        line_end = _end_unclosed_hole(self._code, self._start, end, self._chars)
        return line_end if resume is None else min(resume, line_end)


def _end_unclosed_hole(code: str, start: int, end: int, chars: list[str]) -> int:
    """Undo blanking in a hole that never closed; return its line's end.

    ``end`` is how far the hole scan reached.
    """
    chars[start:end] = code[start:end]
    newline = code.find("\n", start, end)
    return end if newline < 0 else newline


def _closes_outer_raw_string(code: str, token: re.Match[str], after: int, escape: str) -> bool:
    """Whether ``token``, a quote run inside a raw-string hole, is the close.

    It is when it has no prefix, is at least as long as the outer raw
    string's opening run (``escape``), and opens a string that never closes.
    """
    quotes = token.group("quotes")
    if len(escape) < 3 or not quotes or token.group("prefix") or len(quotes) < len(escape):
        return False
    close_start = after - len(quotes)
    ends_on_run = code.startswith(quotes, close_start)
    run_overlaps_opening = close_start < token.end()
    return not ends_on_run or run_overlaps_opening


def _csharp_format_span_end(code: str, start: int, escape: str) -> int:
    """Index of the character that ends the format specifier at ``start``.

    A specifier ends at "}". It cannot hold a newline, an unescaped quote,
    or a "{", so meeting one first means the hole is malformed; the caller
    then leaves the text visible. ``escape`` is as in ``csharp_hole_end``.
    """
    index = start
    while index < len(code):
        if (
            escape == "\\"
            and code[index] == "\\"
            and code[index + 1 : index + 2] not in ("", "\n", "{", "}")
        ):
            index += 2
            continue
        if escape == '"' and code.startswith('""', index):
            index += 2
            continue
        if code[index] in '}{\n"':
            return index
        index += 1
    return index


# Words that start a statement or declaration. One at the top level of a hole
# means the hole is malformed and its "}" belongs to other code.
# Only reserved words: contextual keywords such as record, where and var are
# also legal names, as in {record.Total:N2}.
_CSHARP_STATEMENT_WORD_RE = re.compile(
    r"(?:case|class|struct|interface|enum|goto|return|void|public"
    r"|private|protected|internal|static|namespace|using)\b"
)


def _continues_identifier(before: str) -> bool:
    """Whether ``before`` continues a name, so the next word is not a keyword.

    A word after "@" is a verbatim identifier. A reserved word after "."
    stays a keyword, because only "@" lets one name a member.
    """
    return before.isalnum() or before in ("_", "@")


def _ends_format_context(code: str, index: int) -> bool:
    """Whether the top-level character at ``index`` rules out a later specifier.

    A ";" or a statement word such as ``case`` or ``class`` means the hole
    is malformed. A "?" may open an
    unparenthesized ternary, unless it is part of "?." or "??", or is an
    unspaced "?[" such as ``items?[0]``. A spaced " ?[" reads as a ternary
    over a collection expression.
    """
    char = code[index]
    if char == ";":
        return True
    if char.isalpha() and not _continues_identifier(code[index - 1 : index]):
        return _CSHARP_STATEMENT_WORD_RE.match(code, index) is not None
    if char != "?":
        return False
    before, after = code[index - 1 : index], code[index + 1 : index + 2]
    if before == "?" or after in (".", "?"):
        return False
    return after != "[" or before.isspace()
