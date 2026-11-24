"""Scan C# interpolation holes and attribute arguments for doc-accuracy.

A hole is the ``{...}`` code inside an interpolated string. It stays
visible, but literals inside it are blanked and a format specifier such as
``:N2`` is blanked as literal text. ``csharp_literals.py`` drives this scan
and passes in its own token skipper, so this module imports no sibling.

``blank_csharp_attribute_named_args`` runs after the literal blanker. In
``[DllImport("k32", EntryPoint = "Beep")]`` the name ``EntryPoint`` is a
property that the attribute's own type defines, not a repository symbol,
so it is blanked. Attribute names, positional arguments, and
``typeof``/``nameof`` operands stay visible.

Standard library only: the doc-accuracy skill runs on the host's Python.
"""

from __future__ import annotations

import re
from collections.abc import Callable

__all__ = [
    "CSHARP_TOKEN_START_RE",
    "SkipToken",
    "blank_csharp_attribute_named_args",
    "blank_span",
    "csharp_hole_end",
    "line_end",
]

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
    else where the scan stopped. ``escape`` is the enclosing
    string's kind: "\\" regular, '"' verbatim, or the raw opening run.
    ``skip_token`` passes one comment or literal and reports if it closed.

    The hole is code and stays visible. Literals inside it are blanked and
    comments skipped. A format specifier, as in ``{price:N2}``, is blanked
    once its "}" arrives; a ":" counts only before any newline, top-level
    ";", statement word, or ternary "?" ("?.", "??" and an unspaced "?[" are
    not), and a specifier meeting a newline, quote, or "{" stays visible.

    In regular and verbatim strings a hole is unclosed once it spans more
    than ``_MAX_HOLE_LINES`` lines. In any string kind it is unclosed at the
    snippet end, when a nested literal or comment lacks its close, when an
    interpolated string opens on a later line, or, in a raw string, at a
    quote run that closes nothing. The enclosing string then reports itself
    unclosed, so ``blank_csharp_literals`` leaves the whole snippet
    unblanked.

    Accepted limit: a string missing its close quote that pairs with a
    later quote on its own line looks closed, so code between the two
    quotes, and after them on that line, can still be blanked.
    """
    return _HoleScan(code, chars, escape, start, skip_token).run()


# A hole in a regular or verbatim string spanning more lines than this is
# treated as unclosed, since such a hole is far likelier a missing "}".
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
        return self._index, False

    def _step(self) -> int | None:
        """Advance past one token or character; return the hole end once known."""
        token = CSHARP_TOKEN_START_RE.match(self._code, self._index)
        if token is not None:
            return self._token(token)
        char = self._code[self._index]
        if char == "\n" and self._count_lines(1):
            return self._index
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
        if self._lines and "$" in (token.group("prefix") or ""):
            # An interpolated string opening on a later line of this hole
            # would nest one hole per line. Treat this hole as broken here.
            return index
        after, closed = self._skip_token(code, token, self._chars)
        if not closed or _closes_outer_raw_string(code, token, after, self._escape):
            # A nested literal or comment with no close, or a quote run that
            # closes the outer raw string, means this hole is broken.
            return index
        newlines = code.count("\n", index, after)
        if newlines:
            self._format_allowed = False
            if self._count_lines(newlines):
                return index
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


# Comments in code whose literals are already blanked, so "//" in a string
# cannot start one.
_CSHARP_COMMENT_RE = re.compile(r"(?s)//[^\n]*|/\*.*?(?:\*/|\Z)")

# An attribute section is a "[" in declaration position. Skipping blank space
# and comments, the code before it is the snippet start, ";", "{", "}", the
# "]" of an attribute section (chained sections), or "(" or "," (a parameter
# attribute). An indexer follows a name, and a collection expression usually
# follows "=", "return" or an operator, so neither qualifies. Accepted limit:
# an attribute after "=" (a lambda attribute), after "<" (a type parameter
# attribute), or directly inside "[" (a lambda attribute in a collection
# expression) is not detected, so its named arguments are still reported.
_CSHARP_ATTRIBUTE_CONTEXT = frozenset(";{}(,")

# After the closing "]", the next code must start a declaration: a name
# (with or without "@"), "[", "(" (a tuple return type), "~" (a finalizer),
# or the snippet end. A collection expression or list pattern is followed by
# ")", ",", ";", ".", "=", "=>", an operator, or a keyword such as "is" or
# "when", so it does not qualify. A list pattern can also be followed by a
# designation name, "@" escaped or not. The "after" group captures what
# follows that name so the caller can reject it; see _is_attribute_follower.
_CSHARP_ATTRIBUTE_FOLLOWER_RE = re.compile(
    r"\s*(?:(?P<end>\Z)|[\[(~]|(?!(?:is|as|when|and|or|not|with|switch)\b)"
    r"(?P<name>@?[A-Za-z_]\w*)\b(?P<after>\s*(?:=>|(?:when|and|or)\b|[,)]))?)"
)

# A section at the very end of a snippet may be a trailing collection
# expression, so it counts as an attribute only with an explicit target.
_CSHARP_ATTRIBUTE_TARGET_RE = re.compile(
    r"\s*(?:assembly|module|field|event|method|param|property|return|type|typevar)\s*:(?!:)"
)

# The word before a "{" that opens a switch expression's arms.
_CSHARP_SWITCH_BRACE_RE = re.compile(r"\bswitch\s*$")

# Accessors may be expression-bodied, so "get =>" still ends an attribute.
_CSHARP_ACCESSOR_NAMES = frozenset({"get", "set", "init", "add", "remove"})

# Inside a section, a name right after "(" or "," and before "=" or ":"
# names a property or parameter that the attribute's own type defines. A
# ternary operand follows "?" and a lambda parameter precedes "=>", so both
# stay visible.
_CSHARP_ATTRIBUTE_NAMED_ARG_RE = re.compile(r"[(,]\s*(@?[A-Za-z_]\w*)(?=\s*(?:=(?![=>])|:(?!:)))")


def _csharp_attribute_section_end(code: str, start: int) -> tuple[int, bool]:
    """Scan a section opened just before ``start``; return (stop, closed).

    ``stop`` is the index of the closing "]" when ``closed`` is true, else
    where the scan gave up: a ";", a "{" outside the argument list, or the
    end of the snippet. Attribute arguments hold no statements.
    """
    depth, paren = 1, 0
    for index in range(start, len(code)):
        char = code[index]
        if char == ";" or (paren == 0 and char == "{"):
            return index, False
        if char in "()":
            paren += 1 if char == "(" else -1
        elif char in "[]":
            depth += 1 if char == "[" else -1
            if depth == 0:
                return index, True
    return len(code), False


def _is_attribute_follower(view: str, start: int, stop: int, opener: int) -> bool:
    """Whether the section from ``start`` to the "]" at ``stop`` is an attribute.

    ``opener`` is the index of the innermost open bracket around the
    section, or -1 at the top level. A section directly inside "[" is
    treated as a nested list pattern or collection element, never an
    attribute; a lambda attribute there is the one accepted miss, and it
    only over-reports. At the snippet end a section needs an explicit
    target such as ``assembly:``. A name followed by "when", "and" or "or"
    is a pattern designation. A name followed by "=>" is one too, unless it
    is an accessor outside a switch expression's braces. A lone name
    followed by "," or ")" inside parentheses is a designation in a tuple or
    positional pattern; inside braces it is an enum member.
    """
    enclosing = view[opener] if opener >= 0 else ""
    if enclosing == "[":
        return False
    follower = _CSHARP_ATTRIBUTE_FOLLOWER_RE.match(view, stop + 1)
    if follower is None:
        return False
    if follower.group("end") is not None:
        return _CSHARP_ATTRIBUTE_TARGET_RE.match(view, start) is not None
    after = (follower.group("after") or "").strip()
    if after in ("when", "and", "or"):
        return False
    if after == "=>":
        in_switch = enclosing == "{" and _CSHARP_SWITCH_BRACE_RE.search(view, 0, opener)
        return follower.group("name") in _CSHARP_ACCESSOR_NAMES and not in_switch
    return not (after in (",", ")") and enclosing == "(")


def _enclosing_brackets(view: str) -> list[int]:
    """For each index, where the innermost bracket open before it is, or -1."""
    closers = {")": "(", "]": "[", "}": "{"}
    stack: list[int] = []
    enclosing = []
    for index, char in enumerate(view):
        enclosing.append(stack[-1] if stack else -1)
        if char in "([{":
            stack.append(index)
        elif char in closers and stack and view[stack[-1]] == closers[char]:
            stack.pop()
    return enclosing


def _previous_code_index(view: str, index: int) -> int:
    """Index of the last non-blank character before ``index``, or -1."""
    index -= 1
    while index >= 0 and view[index].isspace():
        index -= 1
    return index


def blank_csharp_attribute_named_args(code: str) -> str:
    """Blank named-argument names inside attribute argument lists.

    Expects literals already blanked, so brackets and parentheses in strings
    do not move a section. Comments are blanked in a private view used only
    to find sections. Attribute names, positional arguments, and
    ``typeof``/``nameof`` operands stay visible. Every section scan starts
    past the previous one, so the pass stays linear.
    """
    view = _CSHARP_COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), code)
    chars = list(code)
    enclosing = _enclosing_brackets(view)
    scanned_to = 0
    attribute_closes: set[int] = set()
    for opening in re.finditer(r"\[", view):
        if opening.start() < scanned_to:
            continue
        before = _previous_code_index(view, opening.start())
        in_context = before < 0 or view[before] in _CSHARP_ATTRIBUTE_CONTEXT
        if not in_context and before not in attribute_closes:
            continue
        stop, closed = _csharp_attribute_section_end(view, opening.end())
        scanned_to = stop
        if not closed or not _is_attribute_follower(
            view, opening.end(), stop, enclosing[opening.start()]
        ):
            continue
        attribute_closes.add(stop)
        for named in _CSHARP_ATTRIBUTE_NAMED_ARG_RE.finditer(view, opening.end(), stop):
            blank_span(chars, named.start(1), named.end(1))
    return "".join(chars)
