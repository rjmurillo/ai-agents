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
import os
import stat
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

_TERMINATORS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


class ScanError(RuntimeError):
    """Raised when the gate cannot inspect its declared source corpus."""


def _clean_git_env() -> dict[str, str]:
    """Return the process environment without ambient Git repository pointers."""
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }


def _tracked_python_files(repo_root: Path) -> list[Path]:
    """Return tracked ``*.py`` files via ``git ls-files``."""
    try:
        result = subprocess.run(
            [
                "git",
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
                "*.py",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=_clean_git_env(),
        )
    except OSError as exc:
        raise ScanError(f"git could not list Python files: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or f"git exited {result.returncode}"
        raise ScanError(f"git could not list Python files: {detail}")

    files = [repo_root / entry for entry in result.stdout.split("\0") if entry]
    if not files:
        raise ScanError("git reported zero tracked or untracked Python files")
    return files


def _nested_statement_blocks(statement: ast.stmt) -> Iterator[list[ast.stmt]]:
    """Yield executable child blocks without entering nested definitions."""
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return
    for attribute in ("body", "orelse", "finalbody"):
        block = getattr(statement, attribute, None)
        if isinstance(block, list) and all(isinstance(item, ast.stmt) for item in block):
            yield block
    for handler in getattr(statement, "handlers", ()):
        yield handler.body
    for case in getattr(statement, "cases", ()):
        yield case.body


def _find_in_block(
    statements: list[ast.stmt],
    path: Path,
    function_name: str,
) -> list[tuple[Path, str, int]]:
    """Find unreachable statements in this block and its executable child blocks."""
    findings = [
        (path, function_name, statements[index + 1].lineno)
        for index in range(len(statements) - 1)
        if isinstance(statements[index], _TERMINATORS)
    ]
    for statement in statements:
        for block in _nested_statement_blocks(statement):
            findings.extend(_find_in_block(block, path, function_name))
    return findings


def _scan(repo_root: Path) -> tuple[list[tuple[Path, str, int]], int]:
    """Return ``(file, function_name, lineno)`` for each unreachable statement.

    A statement is unreachable when it follows a ``return``, ``raise``,
    ``continue``, or ``break`` within the same block of a function body.
    Only the immediately following statement is reported to avoid redundant
    cascaded hits.
    """
    files = _tracked_python_files(repo_root)
    findings: list[tuple[Path, str, int]] = []
    for path in files:
        try:
            mode = path.stat(follow_symlinks=False).st_mode
        except OSError as exc:
            raise ScanError(f"Python source is missing: {path}") from exc
        if not stat.S_ISREG(mode):
            raise ScanError(f"Python source is not a regular file: {path}")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            raise ScanError(f"could not analyze Python source {path}: {exc}") from exc
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                findings.extend(_find_in_block(node.body, path, node.name))
    return findings, len(files)


def find_unreachable_statements(repo_root: Path) -> list[tuple[Path, str, int]]:
    """Return ``(file, function_name, lineno)`` for each unreachable statement."""
    return _scan(repo_root)[0]


def validate_unreachable_code(repo_root: Path) -> bool:
    """Return ``True`` when no unreachable statements are found, ``False`` otherwise."""
    if not repo_root.is_dir():
        raise ScanError(f"repository root not found: {repo_root}")

    findings, scanned_files = _scan(repo_root)
    if not findings:
        print(
            f"check_unreachable_code: OK. Scanned {scanned_files} Python file(s); "
            "0 unreachable statements."
        )
        return True

    for path, func_name, lineno in findings:
        print(
            f"  unreachable: {path}:{lineno} in {func_name}()",
            file=sys.stderr,
        )
    print(
        f"\n{len(findings)} unreachable statement(s) found in "
        f"{scanned_files} Python file(s). "
        "Remove code after return/raise/continue/break.",
        file=sys.stderr,
    )
    return False


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) > 1:
        print("error: expected at most one repository root", file=sys.stderr)
        return 2
    repo_root = Path(args[0]).resolve() if args else Path.cwd()
    try:
        return 0 if validate_unreachable_code(repo_root) else 1
    except ScanError as exc:
        print(f"error: unreachable-code scan did not run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
