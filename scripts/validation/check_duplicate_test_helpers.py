#!/usr/bin/env python3
"""Gate: no duplicate module-level test helper definitions.

Ruff F811 ignores names that match ``lint.dummy-variable-rgx``. Ruff documents
that F811 ignores dummy variables, and the default regex matches `_helper`.
This gate covers the repository-specific gap for tests, where helpers are often
private by naming convention and a later definition silently replaces the
earlier one.

Exit codes (ADR-035):
    0 - Success (no duplicate module-level test helpers found)
    1 - Logic error (one or more duplicate helpers found)
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


def _is_git_root(repo_root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return Path(result.stdout.strip()).resolve() == repo_root.resolve()


def _tracked_test_files(repo_root: Path) -> list[Path]:
    """Return tracked and untracked ``tests/**/*.py`` files when possible."""
    if not _is_git_root(repo_root):
        return _walk_test_files(repo_root)

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "--",
                "tests",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return _walk_test_files(repo_root)

    paths = []
    for line in result.stdout.splitlines():
        path = repo_root / line
        if path.suffix == ".py" and path.is_file():
            paths.append(path)
    return paths


def _walk_test_files(repo_root: Path) -> list[Path]:
    tests_root = repo_root / "tests"
    if not tests_root.is_dir():
        return []

    files: list[Path] = []
    for path in tests_root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.relative_to(repo_root).parts):
            continue
        files.append(path)
    return files


def find_duplicate_module_level_helpers(repo_root: Path) -> list[tuple[Path, str, int, int]]:
    """Return duplicate module-level test helper definitions.

    Each tuple is ``(path, name, first_line, duplicate_line)``. Only top-level
    ``def`` and ``async def`` statements are considered. Nested helpers and class
    methods have their own scopes, so they are not reported.
    """
    findings: list[tuple[Path, str, int, int]] = []
    for path in _tracked_test_files(repo_root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError):
            continue

        seen: dict[str, int] = {}
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            previous = seen.get(node.name)
            if previous is not None:
                findings.append((path, node.name, previous, node.lineno))
            else:
                seen[node.name] = node.lineno
    return findings


def validate_duplicate_test_helpers(repo_root: Path) -> bool:
    """Return True when no duplicate module-level test helpers are found."""
    findings = find_duplicate_module_level_helpers(repo_root)
    if not findings:
        return True

    print(
        f"[FAIL] {len(findings)} duplicate module-level test helper definition(s) found:",
        file=sys.stderr,
    )
    for path, name, first_line, duplicate_line in findings:
        rel = path.relative_to(repo_root) if path.is_relative_to(repo_root) else path
        print(f"  {rel}:{first_line} and {duplicate_line} duplicate {name}()", file=sys.stderr)
    print("\nFix: rename or merge the duplicate helper definitions.", file=sys.stderr)
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    return 0 if validate_duplicate_test_helpers(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
