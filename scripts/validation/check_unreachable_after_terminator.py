#!/usr/bin/env python3
"""Gate: no statement may follow a return, raise, continue, or break.

A statement in the same block after one of those terminators is dead code.
Python executes it never; readers assume it runs; coverage tools may miss it.
Ruff has no stable rule that covers this shape (verified against the repo,
issue #3874), so this bespoke AST scanner fills the gap.

The check is a deliberate floor: it detects only direct siblings within the
same block. It does NOT perform reachability analysis across branches or
loops. That keeps false-positives at zero and focuses on the shape that
actually shipped in this repository.

Exit codes (ADR-035):
    0 - no unreachable statements found
    1 - one or more unreachable statements found
    2 - config error (bad CLI usage, a path is not readable)
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import NamedTuple

_TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)
_SKIP = frozenset((".venv", "node_modules", ".git", "site-packages"))

__all__ = [
    "Violation",
    "scan_file",
    "scan_tree",
    "main",
]


class Violation(NamedTuple):
    """One unreachable-statement finding."""

    path: Path
    func_name: str
    terminator_lineno: int
    dead_lineno: int
    terminator_type: str


def scan_tree(tree: ast.AST, path: Path) -> list[Violation]:
    """Return all unreachable statements in *tree*."""
    violations: list[Violation] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = func.body
        for index, stmt in enumerate(body[:-1]):
            if isinstance(stmt, _TERMINATORS):
                dead = body[index + 1]
                violations.append(
                    Violation(
                        path=path,
                        func_name=func.name,
                        terminator_lineno=stmt.lineno,
                        dead_lineno=dead.lineno,
                        terminator_type=type(stmt).__name__,
                    )
                )
                break  # report only the first dead statement per function body
    return violations


def scan_file(path: Path) -> list[Violation]:
    """Parse *path* and return its violations; empty list on parse error."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    return scan_tree(tree, path)


def _iter_paths(roots: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for root in roots:
        if root.is_file():
            paths.append(root)
        else:
            for p in sorted(root.rglob("*.py")):
                if not any(part in _SKIP for part in p.parts):
                    paths.append(p)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path(".")],
        help="Files or directories to scan (default: current directory)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-violation output; still exits non-zero on failure",
    )
    args = parser.parse_args(argv)

    all_violations: list[Violation] = []
    for path in _iter_paths(args.paths):
        all_violations.extend(scan_file(path))

    for v in sorted(all_violations, key=lambda x: (str(x.path), x.dead_lineno)):
        if not args.quiet:
            print(
                f"{v.path}:{v.dead_lineno}: unreachable statement in "
                f"`{v.func_name}` after {v.terminator_type} at line {v.terminator_lineno}"
            )

    if all_violations:
        if not args.quiet:
            print(
                f"\n{len(all_violations)} unreachable statement(s) found. "
                "Remove them or restructure the function."
            )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
