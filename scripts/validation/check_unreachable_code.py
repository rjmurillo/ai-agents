#!/usr/bin/env python3
"""Blocking gate: no statement may follow a terminator in the same block.

A statement placed after ``return``, ``raise``, ``continue``, or ``break``
in the same block never executes. Ruff, mypy, pytest, and the push gate all
passed a change that carried one; it was found by hand afterwards (issue #3874).

The repository has zero unreachable statements today, so this gate adds no
backfill burden.

Scope: first-party ``.py`` files tracked by git. The gate skips ``.venv``,
``node_modules``, ``.git``, ``site-packages``, and other non-source trees.

Exit codes (ADR-035):
    0 - Success (no unreachable statements found)
    1 - Logic error (one or more unreachable statements found)
    2 - Config error (invalid repository root)
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

_SKIP_DIRS = frozenset(
    {
        ".venv",
        "venv",
        ".git",
        "__pycache__",
        "node_modules",
        ".mypy_cache",
        ".ruff_cache",
        "site-packages",
    }
)

_TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def _tracked_python_files(repo_root: Path) -> list[Path]:
    """Return tracked ``*.py`` files via ``git ls-files``."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return [repo_root / line for line in result.stdout.splitlines() if line]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return _walk_python_files(repo_root)


def _walk_python_files(repo_root: Path) -> list[Path]:
    """Filesystem fallback when git is unavailable."""
    files: list[Path] = []
    for path in repo_root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def find_unreachable_statements(repo_root: Path) -> list[tuple[Path, str, int]]:
    """Return ``(file, function_name, lineno)`` for each unreachable statement.

    A statement is unreachable when it follows a ``return``, ``raise``,
    ``continue``, or ``break`` within the same block of a function body.
    Only the immediately following statement is reported to avoid redundant
    cascaded hits.
    """
    findings: list[tuple[Path, str, int]] = []
    for path in _tracked_python_files(repo_root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = node.body
            for index in range(len(body) - 1):
                if isinstance(body[index], _TERMINATORS):
                    findings.append((path, node.name, body[index + 1].lineno))
    return findings


def validate_unreachable_code(repo_root: Path) -> bool:
    """Return ``True`` when no unreachable statements are found, ``False`` otherwise."""
    if not repo_root.is_dir():
        print(f"error: repository root not found: {repo_root}", file=sys.stderr)
        sys.exit(2)

    findings = find_unreachable_statements(repo_root)
    if not findings:
        return True

    for path, func_name, lineno in findings:
        print(
            f"  unreachable: {path}:{lineno} in {func_name}()",
            file=sys.stderr,
        )
    print(
        f"\n{len(findings)} unreachable statement(s) found. "
        "Remove code after return/raise/continue/break.",
        file=sys.stderr,
    )
    return False


def main() -> None:
    """CLI entry point."""
    repo_root = Path.cwd()
    if not validate_unreachable_code(repo_root):
        sys.exit(1)
    print("check_unreachable_code: OK")


if __name__ == "__main__":
    main()
