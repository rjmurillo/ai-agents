#!/usr/bin/env python3
"""Gate: detect test functions defined inside other functions.

A function whose name starts with ``test_`` and that is nested inside another
function body is never collected by pytest. The file parses, the suite runs
green, and the regression guard is silently absent. This pattern was found live
in PR #3688 (four tests nested inside ``_repo_where_a_rename_repadded_the_number``
below its ``return``), and nothing in the existing gate set caught it. See
issue #3879 for the full incident report.

Discriminator: a ``test_*`` function with any enclosing ``FunctionDef`` in the
AST ancestor chain. Nested *classes* (``TestSomething.TestInner``) are collected
by pytest and are NOT flagged.

Exit codes (ADR-035):
    0 - Success (no nested test functions found)
    1 - Logic error (one or more uncollectable test functions found)
    2 - Config error (invalid repository root)
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

_SKIP_DIRS = frozenset(
    {".venv", "venv", ".git", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache"}
)


class _NestedTestFinder(ast.NodeVisitor):
    """Walk an AST and record ``test_*`` functions nested inside functions."""

    def __init__(self) -> None:
        self.findings: list[tuple[int, str]] = []
        self._func_depth = 0

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.name.startswith("test_") and self._func_depth > 0:
            self.findings.append((node.lineno, node.name))
        self._func_depth += 1
        self.generic_visit(node)
        self._func_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)


def _tracked_test_files(repo_root: Path) -> list[Path]:
    """Return tracked ``test_*.py`` files via ``git ls-files``."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "tests/*/test_*.py", "tests/test_*.py"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=15,
        )
        rels = [line for line in completed.stdout.splitlines() if line.strip()]
        return [repo_root / rel for rel in rels]
    except (OSError, subprocess.SubprocessError):
        return _walk_test_files(repo_root)


def _walk_test_files(repo_root: Path) -> list[Path]:
    """Fallback when git is unavailable."""
    found: list[Path] = []
    for path in repo_root.rglob("test_*.py"):
        if any(part in _SKIP_DIRS for part in path.relative_to(repo_root).parts):
            continue
        found.append(path)
    return found


def find_nested_tests(repo_root: Path) -> list[tuple[Path, int, str]]:
    """Return ``(path, lineno, func_name)`` for every uncollectable test function.

    A test function is uncollectable when it is defined inside the body of
    another function. Nested classes (``ClassDef`` enclosing ``test_*``) are
    NOT flagged because pytest collects them.
    """
    results: list[tuple[Path, int, str]] = []
    for path in _tracked_test_files(repo_root):
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, UnicodeError, SyntaxError):
            continue
        finder = _NestedTestFinder()
        finder.visit(tree)
        for lineno, name in finder.findings:
            results.append((path, lineno, name))
    return results


def validate_no_nested_tests(repo_root: Path) -> bool:
    """Return True when no tracked test file contains nested test functions.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr.py``.
    """
    findings = find_nested_tests(repo_root)
    if not findings:
        return True
    print(
        f"[FAIL] {len(findings)} test function(s) are nested inside another function "
        "and will never be collected by pytest:",
        file=sys.stderr,
    )
    for path, lineno, name in findings:
        rel = path.relative_to(repo_root) if path.is_relative_to(repo_root) else path
        print(f"  {rel}:{lineno}  {name}()", file=sys.stderr)
    print(
        "\nFix: move each flagged function to module level or into a class body.",
        file=sys.stderr,
    )
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    return 0 if validate_no_nested_tests(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
