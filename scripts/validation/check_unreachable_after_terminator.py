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

Registered worktrees are skipped. Each one holds a full second copy of the
tree, so walking them multiplies the file count by the number of worktrees and
trips this gate's timeout without finding anything new. The skip matches parts
relative to each walk root, not absolute parts, because a repository that
itself lives under a directory named `worktrees` would otherwise be skipped
whole and the gate would pass by scanning nothing (issue #4160).

Exit codes (ADR-035):
    0 - no unreachable statements found
    1 - one or more unreachable statements found
    2 - config error (bad CLI usage, a path is not readable)
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

_TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)
_SKIP = frozenset((".venv", "node_modules", ".git", "site-packages", "worktrees"))
_BLOCK_ATTRS = ("body", "orelse", "finalbody")

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
        for body, is_root_body in _function_statement_blocks(func):
            terminators = _TERMINATORS if is_root_body else (ast.Return, ast.Raise)
            violations.extend(_scan_statement_block(body, path, func.name, terminators))
    return violations


def _function_statement_blocks(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[tuple[list[ast.stmt], bool]]:
    """Yield every executable statement block owned by ``func``."""
    stack = [(func.body, True)]
    while stack:
        body, is_root_body = stack.pop()
        yield body, is_root_body
        for statement in body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            stack.extend((block, False) for block in _child_statement_blocks(statement))


def _child_statement_blocks(statement: ast.stmt) -> list[list[ast.stmt]]:
    blocks: list[list[ast.stmt]] = []
    for attr in _BLOCK_ATTRS:
        value = getattr(statement, attr, None)
        if isinstance(value, list) and all(isinstance(item, ast.stmt) for item in value):
            blocks.append(value)
    if isinstance(statement, ast.Try):
        blocks.extend(handler.body for handler in statement.handlers)
    return blocks


def _scan_statement_block(
    body: list[ast.stmt],
    path: Path,
    func_name: str,
    terminators: tuple[type[ast.stmt], ...],
) -> list[Violation]:
    for index, stmt in enumerate(body[:-1]):
        if isinstance(stmt, terminators):
            dead = body[index + 1]
            return [
                Violation(
                    path=path,
                    func_name=func_name,
                    terminator_lineno=stmt.lineno,
                    dead_lineno=dead.lineno,
                    terminator_type=type(stmt).__name__,
                )
            ]
    return []


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
                if not any(part in _SKIP for part in p.relative_to(root).parts):
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
