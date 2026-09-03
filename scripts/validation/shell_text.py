#!/usr/bin/env python3
"""Shell text helpers shared by the validation gates.

One authoritative place that knows where a shell comment starts and where one
statement ends. A second hand-rolled copy drifts from this one on the first
quoting edge case it meets, and a caller that scans a raw line with its own
regex instead learns nothing about separators, escaping, or repetition.
"""

from __future__ import annotations

# `;` ends a statement, `&&`, `||` and `|` chain one to the next, and a lone
# `&` backgrounds it. Runs of them collapse, so `&&` is not read as two empty
# statements. `>` is deliberately absent: a redirect belongs to its statement.
_SEPARATORS = frozenset(";&|")


def strip_hash_comments(text: str) -> str:
    """Return ``text`` with shell comments removed, preserving line count.

    Quote-aware, because ``#`` inside a string is data rather than a comment:
    ``echo "the # sign"`` keeps its hash. Backslash and backtick escape the
    character after them.

    Line count is preserved, so a caller may pass either a whole block or a
    single line and keep its own line numbering.
    """
    stripped: list[str] = []
    for line in text.splitlines():
        in_single = False
        in_double = False
        escaped = False
        cut_at = len(line)
        for index, char in enumerate(line):
            if escaped:
                escaped = False
                continue
            if char in {"\\", "`"}:
                escaped = True
                continue
            if char == "'" and not in_double:
                in_single = not in_single
                continue
            if char == '"' and not in_single:
                in_double = not in_double
                continue
            if char == "#" and not in_single and not in_double:
                cut_at = index
                break
        stripped.append(line[:cut_at])
    return "\n".join(stripped)


def split_statements(line: str) -> list[tuple[int, str]]:
    """Split one line into ``(column, text)`` statements on shell separators.

    ``column`` is the offset of the statement's first character in the original
    line, so statements stay orderable against each other and against anything
    else measured against that line. Separators inside quotes, and ones the
    previous character escaped, do not split.

    Callers that need to know what a line *does* must go through this rather
    than scanning the raw line, because a raw scan sees only the first
    occurrence of whatever it looks for and cannot tell an argument from the
    terminator stuck to it. ``flock "$LOCK"; git push`` yields ``flock
    "$LOCK"`` and ``git push``, not one blob whose argument token is
    ``$LOCK";``.
    """
    statements: list[tuple[int, str]] = []
    start = 0
    in_single = False
    in_double = False
    escaped = False
    index = 0
    while index < len(line):
        char = line[index]
        if escaped:
            escaped = False
        elif char in {"\\", "`"}:
            escaped = True
        elif char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char in _SEPARATORS and not in_single and not in_double:
            statements.append((start, line[start:index]))
            while index + 1 < len(line) and line[index + 1] in _SEPARATORS:
                index += 1
            start = index + 1
        index += 1
    statements.append((start, line[start:]))
    return [(column, text) for column, text in statements if text.strip()]
