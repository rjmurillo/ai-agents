"""Blank the named-argument names inside C# attribute argument lists.

In ``[DllImport("k32", EntryPoint = "Beep")]`` the name ``EntryPoint`` is a
property that the attribute's own type defines, not a repository symbol,
so doc-accuracy should not report it. Run this after
``csharp_literals.blank_csharp_literals``, which blanks the string text.
Attribute names, positional arguments, and ``typeof``/``nameof`` operands
stay visible.

Standard library only: the doc-accuracy skill runs on the host's Python.
"""

from __future__ import annotations

import re

from csharp_holes import blank_span

__all__ = ["blank_csharp_attribute_named_args"]


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
            blank_span(chars, named.start(1), named.end(1))
    return "".join(chars)
