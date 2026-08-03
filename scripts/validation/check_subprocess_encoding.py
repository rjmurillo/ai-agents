"""Subprocess encoding convention checker.

Detects subprocess.run / subprocess.Popen / subprocess.check_output /
subprocess.check_call calls that decode text (via ``text=True`` or
``encoding=...``) but omit ``errors=``. A missing ``errors=`` means decode
errors raise UnicodeDecodeError, which silently drops output or crashes the
caller. The canonical form is::

    subprocess.run(..., text=True, encoding="utf-8", errors="replace")

Exit codes (AGENTS.md contract):
    0  - ok: no violations found
    1  - violations found
    2  - config error (bad arguments, baseline missing)
    3  - external error (could not parse a file)

Usage::

    # Check a single file
    uv run --frozen python scripts/validation/check_subprocess_encoding.py path/to/file.py

    # Check all tracked Python files
    uv run --frozen python scripts/validation/check_subprocess_encoding.py --all

    # Check only changed files (for pre-commit hooks)
    uv run --frozen python scripts/validation/check_subprocess_encoding.py --changed-files

Refs #4261.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

__all__ = ["check_file", "main"]

# Subprocess functions that accept text-mode keyword arguments.
_SUBPROCESS_FUNCS = frozenset(
    {"subprocess.run", "subprocess.Popen", "subprocess.check_output", "subprocess.check_call"}
)

# Files under this prefix are exempt (intentional bad-byte test fixtures).
_FIXTURE_PREFIX = "tests/hooks/fixtures/"


def _is_subprocess_call(node: ast.Call) -> bool:
    """Return True if node is a call to a known subprocess function."""
    func = node.func
    if isinstance(func, ast.Attribute):
        # Handle ``subprocess.run(...)``
        if isinstance(func.value, ast.Name) and func.value.id == "subprocess":
            return f"subprocess.{func.attr}" in _SUBPROCESS_FUNCS
    if isinstance(func, ast.Name):
        # Handle bare ``run(...)`` after ``from subprocess import run``
        return func.id in {f.split(".")[1] for f in _SUBPROCESS_FUNCS}
    return False


def _keyword_names(call: ast.Call) -> frozenset[str]:
    """Return the set of keyword argument names used in a call."""
    return frozenset(kw.arg for kw in call.keywords if kw.arg is not None)


def _uses_text_mode(keywords: frozenset[str]) -> bool:
    """Return True if the call uses text mode (text= or encoding=)."""
    return "text" in keywords or "encoding" in keywords


def _has_errors_kwarg(keywords: frozenset[str]) -> bool:
    """Return True if the call already specifies errors=."""
    return "errors" in keywords


def check_file(path: Path) -> list[tuple[int, str]]:
    """Parse *path* and return (lineno, message) for each violation.

    Returns an empty list for files that do not use subprocess, and raises
    ValueError if the file cannot be parsed.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise ValueError(f"syntax error in {path}: {exc}") from exc

    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_subprocess_call(node):
            continue
        keywords = _keyword_names(node)
        if _uses_text_mode(keywords) and not _has_errors_kwarg(keywords):
            func_name = (
                ast.unparse(node.func)
                if hasattr(ast, "unparse")
                else "subprocess call"
            )
            violations.append(
                (
                    node.lineno,
                    f"{func_name} uses text mode but omits errors=; "
                    "add errors=\"replace\" (or errors=\"strict\" if intentional)",
                )
            )
    return violations


def _tracked_python_files(repo_root: Path) -> list[Path]:
    """Return all tracked .py files in the repository."""
    result = subprocess.run(
        ["git", "ls-files", "*.py", "**/*.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=repo_root,
    )
    if result.returncode != 0:
        return []
    return [repo_root / line for line in result.stdout.splitlines() if line.endswith(".py")]


def _changed_python_files(repo_root: Path) -> list[Path]:
    """Return .py files changed relative to HEAD (staged and unstaged)."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACM", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=repo_root,
    )
    if result.returncode != 0:
        return []
    paths = [
        repo_root / line
        for line in result.stdout.splitlines()
        if line.endswith(".py")
    ]
    # Also include staged files not in HEAD (new files)
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=repo_root,
    )
    if staged.returncode == 0:
        for line in staged.stdout.splitlines():
            if line.endswith(".py"):
                p = repo_root / line
                if p not in paths:
                    paths.append(p)
    return paths


def _is_exempt(path: Path, repo_root: Path) -> bool:
    """Return True if *path* is exempt from the convention."""
    try:
        rel = path.relative_to(repo_root)
    except ValueError:
        return False
    return str(rel).startswith(_FIXTURE_PREFIX)


def _print_violations(
    path: Path, repo_root: Path, violations: list[tuple[int, str]]
) -> int:
    """Print violations for *path* and return the count."""
    count = 0
    for lineno, msg in violations:
        try:
            rel = path.relative_to(repo_root)
        except ValueError:
            rel = path
        print(f"{rel}:{lineno}: {msg}")
        count += 1
    return count


def _exit_code(total_violations: int) -> int:
    """Return the exit code for the checker."""
    if total_violations:
        print(
            f"\ncheck_subprocess_encoding: {total_violations} violation(s) found.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--all",
        action="store_true",
        dest="all_files",
        help="Check all tracked Python files (default when no paths given).",
    )
    mode.add_argument(
        "--changed-files",
        action="store_true",
        dest="changed_files",
        help="Check only files changed relative to HEAD.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Specific files to check.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.strip()
    )

    if args.paths:
        files = list(args.paths)
    elif args.changed_files:
        files = _changed_python_files(repo_root)
    else:
        # --all is the default when no paths given
        files = _tracked_python_files(repo_root)

    if not files:
        print("check_subprocess_encoding: no files to check")
        return 0

    total_violations = 0
    for path in sorted(files):
        if _is_exempt(path, repo_root):
            continue
        if not path.is_file():
            continue
        try:
            violations = check_file(path)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3
        total_violations += _print_violations(path, repo_root, violations)

    return _exit_code(total_violations)


if __name__ == "__main__":
    raise SystemExit(main())
