"""Blank C# string literal text and attribute named-argument names.

The doc-accuracy scanner uses this before it looks for C# identifiers, so a
name that appears only inside a literal, or as an attribute's named
argument, is not reported as an unresolved symbol.

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

__all__ = ["blank_csharp_attribute_named_args", "blank_csharp_literals"]


# The start of a C# comment or literal. A comment is consumed but kept, so a
# quote inside it opens nothing. "prefix" holds the $ and @ markers of a
# string. The cap keeps a long marker run from being rescanned at every start.
_CSHARP_TOKEN_START_RE = re.compile(r"//|/\*|'|(?P<prefix>[$@]{0,8})(?P<quotes>\"+)")


def _blank_span(chars: list[str], start: int, end: int) -> None:
    """Replace chars[start:end] with spaces, keeping newlines."""
    for index in range(start, end):
        if chars[index] != "\n":
            chars[index] = " "


def _line_end(code: str, index: int) -> int:
    """Index of the newline at or after ``index``, or the end of ``code``."""
    end = code.find("\n", index)
    return len(code) if end < 0 else end


def _csharp_hole_end(code: str, start: int, chars: list[str], escape: str = "") -> tuple[int, bool]:
    """Scan the hole opened at ``start``; return (end, closed).

    ``end`` is just past the "}" that closes the hole when ``closed`` is
    true. Otherwise it is where the enclosing string must stop.

    The hole is code and stays visible, but literals inside it are blanked
    and comments skipped, so a brace or quote in either cannot end the hole
    early. A format specifier, the text after a top-level ":" as in
    ``{price:N2}``, is literal text and is blanked once the "}" that ends it
    is reached. ``escape`` describes the enclosing string: "\\" for a
    regular string, '"' (doubled quote escape) for a verbatim string, and
    the opening quote run for a raw string.

    Valid C# parenthesizes a ternary inside a hole, so its ":" is never
    top-level. For malformed code the blanking stays conservative: a ":"
    counts only before any newline, top-level ";", statement word, or
    ternary "?" in the hole ("?.", "??" and an unspaced "?[" are not
    ternaries), and a specifier that meets a newline, an unescaped quote, or
    a "{" before its "}" is dropped and left visible.

    In a regular or verbatim string a hole may span lines, as C# 11 allows,
    up to ``_MAX_HOLE_LINES``. It counts as never closed when it reaches
    that limit or the snippet end, or when a nested string inside it ends
    without its quote: that quote was the outer string's close, or a hole
    inside it never closed. An unclosed hole has its blanking undone, and
    the enclosing string ends at the hole's opening line end, so the rest of
    that line stays visible code. In a raw string, a quote run that closes
    nothing ends the hole at that run.

    An interpolated string that opens on a later line of the hole also
    marks the hole broken, so holes never nest one per line.

    Accepted limits: a line that chains several unclosed holes or
    unterminated literals, or a string missing its close quote that pairs
    with a later quote on the same line, can still blank the code between.
    A valid hole longer than ``_MAX_HOLE_LINES`` lines, or one holding an
    interpolated string on a later line, is treated as broken; the code
    after its real close can then be blanked up to the next quote.
    """
    return _HoleScan(code, chars, escape, start).run()


# A hole spanning more lines than this is treated as unclosed. The cap keeps
# rescans linear when many unclosed holes stack on consecutive lines.
_MAX_HOLE_LINES = 16


class _HoleScan:
    """Scan state for one interpolation hole; see ``_csharp_hole_end``."""

    def __init__(self, code: str, chars: list[str], escape: str, start: int) -> None:
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

    def run(self) -> tuple[int, bool]:
        """Scan to the hole's end; return (end, closed) as ``_csharp_hole_end``."""
        while self._index < len(self._code):
            done = self._step()
            if done is not None:
                return done, self._closed
        if self._line_bound:
            return self._unclosed(self._index), False
        return self._index, False

    def _step(self) -> int | None:
        """Advance past one token or character; return the hole end once known."""
        token = _CSHARP_TOKEN_START_RE.match(self._code, self._index)
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
        after, closed = _skip_csharp_token(code, token, self._chars)
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
            _blank_span(self._chars, self._index + 1, stop)
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
    then leaves the text visible. ``escape`` is as in ``_csharp_hole_end``.
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
                return _line_end(code, body), False
            index, closed = _csharp_hole_end(code, index, chars, '"' if verbatim else "\\")
            if not closed:
                return index, False
            continue
        if char == '"' and not (verbatim and code.startswith('""', index)):
            if verbatim and _distrusts_verbatim_close(code, body, index):
                chars[body:index] = code[body:index]
                return _line_end(code, body), False
            return index + 1, True
        if char == "\n" and not verbatim:
            chars[body:index] = code[body:index]
            return index, False
        escaped = char == "\\" and not verbatim and code[index + 1 : index + 2] not in ("", "\n")
        doubled = code.startswith(char * 2, index) and char in '{"'
        step = 2 if escaped or doubled else 1
        _blank_span(chars, index, index + step)
        index += step
    chars[body:index] = code[body:index]
    if verbatim:
        return _line_end(code, body), False
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
    if following.isalnum() or following == "_" or '"' in code[close + 1 : _line_end(code, close)]:
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
            end = _line_end(code, index)
            chars[match.end() : end] = code[match.end() : end]
            return end, False
        hole = code.find("{" * dollars, index, close) if dollars else -1
        if hole < 0:
            _blank_span(chars, index, close)
            return close + len(quotes), True
        while code.startswith("{" * (dollars + 1), hole):
            hole += 1
        _blank_span(chars, index, hole)
        index, _ = _csharp_hole_end(code, hole, chars, quotes)


def _csharp_raw_close(code: str, quotes: str, body: int, index: int) -> int:
    """Index of the raw string's closing run at or after ``index``, or -1.

    Follows the C# raw string rules. Text after the opening run makes it a
    single-line string that must close on that line. Otherwise the close
    must sit on its own line after only whitespace, and every content line
    must start with that same whitespace. A run that breaks these rules is
    not a close, so a missing close cannot borrow a later string's quotes.
    """
    opening_line_end = _line_end(code, body)
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
        pos = code.find(quotes, _line_end(code, pos))
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
        _blank_span(chars, match.start() + 1, end - 1)
    return end, closed


def _skip_csharp_token(code: str, match: re.Match[str], chars: list[str]) -> tuple[int, bool]:
    """Pass the comment or literal ``match`` opens; return (end, closed).

    A comment is left unchanged. A literal is blanked. ``closed`` is false
    for a literal without its closing quote or a block comment without
    "*/".
    """
    if match.group(0) == "//":
        return _line_end(code, match.end()), True
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
        while (match := _CSHARP_TOKEN_START_RE.search(code, index)) is not None:
            index, _ = _skip_csharp_token(code, match, chars)
    except RecursionError:
        return None
    return "".join(chars)


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

# After the closing "]", the next code must start a declaration: a name, "@",
# "[", "(" (a tuple return type), "~" (a finalizer), or the snippet end. A
# collection expression or list pattern is followed by ")", ",", ";", ".",
# "=", "=>", an operator, or a keyword such as "is" or "when", so it does not
# qualify. A list pattern can also be followed by a designation name. The
# "after" group captures what follows that name so the caller can reject it;
# see _is_attribute_follower.
_CSHARP_ATTRIBUTE_FOLLOWER_RE = re.compile(
    r"\s*(?:\Z|[@\[(~]|(?!(?:is|as|when|and|or|not|with|switch)\b)"
    r"(?P<name>[A-Za-z_]\w*)\b(?P<after>\s*(?:=>|(?:when|and|or)\b|[,)]))?)"
)

# Accessors may be expression-bodied, so "get =>" still ends an attribute.
_CSHARP_ACCESSOR_NAMES = frozenset({"get", "set", "init", "add", "remove"})

# Inside a section, a name right after "(" or "," and before "=" or ":"
# names a property or parameter that the attribute's own type defines. A
# ternary operand follows "?" and a lambda parameter precedes "=>", so both
# stay visible.
_CSHARP_ATTRIBUTE_NAMED_ARG_RE = re.compile(r"[(,]\s*([A-Za-z_]\w*)(?=\s*(?:=(?![=>])|:(?!:)))")


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


def _is_attribute_follower(view: str, stop: int, enclosing: str) -> bool:
    """Whether the code after the "]" at ``stop`` starts a declaration.

    ``enclosing`` is the innermost open bracket around the section, or "" at
    the top level. A section directly inside "[" is treated as a nested list
    pattern or collection element, never an attribute; a lambda attribute
    there is the one accepted miss, and it only over-reports. A name followed
    by "when", "and" or "or" is a pattern designation. A name followed by
    "=>" is one too, unless it is an accessor. A lone name followed by ","
    or ")" inside parentheses is a designation in a tuple or positional
    pattern; inside braces it is an enum member.
    """
    if enclosing == "[":
        return False
    follower = _CSHARP_ATTRIBUTE_FOLLOWER_RE.match(view, stop + 1)
    if follower is None:
        return False
    after = (follower.group("after") or "").strip()
    if after in ("when", "and", "or"):
        return False
    if after == "=>":
        return follower.group("name") in _CSHARP_ACCESSOR_NAMES
    return not (after in (",", ")") and enclosing == "(")


def _enclosing_brackets(view: str) -> list[str]:
    """For each index, the innermost bracket open before it, or ""."""
    closers = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    enclosing = []
    for char in view:
        enclosing.append(stack[-1] if stack else "")
        if char in "([{":
            stack.append(char)
        elif char in closers and stack and stack[-1] == closers[char]:
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
        if not closed or not _is_attribute_follower(view, stop, enclosing[opening.start()]):
            continue
        attribute_closes.add(stop)
        for named in _CSHARP_ATTRIBUTE_NAMED_ARG_RE.finditer(view, opening.end(), stop):
            _blank_span(chars, named.start(1), named.end(1))
    return "".join(chars)
