#!/usr/bin/env python3
"""Scope rules for the citation-freshness gate (issue #6556).

Extracted from ``check_citation_freshness.py`` at the file-size ceiling,
beside ``citation_anchors.py`` and ``citation_head_state.py``. Two shapes
look like a citation but make no claim about the repository:

* A citation inside a Markdown code fence. A JSON fence cannot hold the
  line-scoped ignore marker, because JSON has no comments, so the marker
  goes on the line directly above the opening fence and exempts the
  whole fence (``enclosing_fence_start``).
* A string literal in a Python test file. An assertion or a data string
  shaped ``path.ext:N`` is test input, not prose (``string_literal_lines``).
  Comments and docstrings stay policed, because they do make claims.
"""

from __future__ import annotations

import ast
import re
from pathlib import PurePosixPath

_FENCE = re.compile(r"^\s*(?P<run>`{3,}|~{3,})")
_CLOSING_FENCE = re.compile(r"^\s*(?P<run>`{3,}|~{3,})\s*$")


def _closes_fence(line: str, opener: str) -> bool:
    """Return whether line closes a fence opened with the opener run."""
    match = _CLOSING_FENCE.match(line)
    if match is None:
        return False
    run = match.group("run")
    return run[0] == opener[0] and len(run) >= len(opener)


def enclosing_fence_start(lines: list[str], line_number: int) -> int | None:
    """Return the 1-based line of the fence opener enclosing line_number.

    Walks from the top so nested and longer fences resolve the way a
    Markdown renderer resolves them. The opener and closer lines are not
    inside the fence. An unclosed fence runs to the end of the file.
    Returns None when the line is outside every fence.
    """
    opener: str | None = None
    opener_line = 0
    for number, line in enumerate(lines[: line_number - 1], 1):
        if opener is None:
            match = _FENCE.match(line)
            if match is not None:
                opener, opener_line = match.group("run"), number
        elif _closes_fence(line, opener):
            opener = None
    return opener_line if opener is not None else None


def _is_tests_python(path: str) -> bool:
    """Return whether path is a Python file under a tests directory."""
    pure = PurePosixPath(path)
    return pure.suffix == ".py" and "tests" in pure.parts[:-1]


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Return ids of the string Constant nodes that are docstrings."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            found.add(id(first.value))
    return found


def string_literal_lines(path: str, lines: list[str]) -> frozenset[int]:
    """Return the 1-based lines inside non-docstring string literals.

    Empty for any file that is not Python under a ``tests`` directory, and
    empty when the file does not parse, so an unreadable file falls back
    to being policed in full rather than silently exempt.
    """
    if not _is_tests_python(path):
        return frozenset()
    try:
        tree = ast.parse("\n".join(lines))
    except SyntaxError:
        return frozenset()
    docstrings = _docstring_nodes(tree)
    covered: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            covered.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return frozenset(covered)
