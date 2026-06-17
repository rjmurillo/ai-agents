#!/usr/bin/env python3
"""Blocking gate: every tracked Python file must parse at the support floor.

Root cause this prevents (issue #2655, regressed by PR #2640): code shipped to
``main`` using ``except OSError, ValueError:`` in ``lsp_gate_state.py`` and
``lsp_health.py``. This is PEP 758 syntax (unparenthesized ``except`` tuples),
which Python 3.14 accepts but 3.13 and earlier reject as a ``SyntaxError``. The
Copilot CLI runs plugin hooks under the host's ambient interpreter (``py -3`` /
``python3``); on a machine where that resolved to 3.13 the PreToolUse dispatcher
hit the ``SyntaxError`` at import, failed closed, and denied every tool call.

Why no existing gate caught it:

  - The dev and CI target is Python 3.14 (``[tool.ruff] target-version=py314``,
    the pytest workflow runs 3.14). On 3.14 the code is *valid*, so it compiles,
    imports, and tests pass. The defect only appears under the floor declared in
    ``pyproject.toml`` (``requires-python = ">=3.10"``), which is the range the
    host interpreter may actually be.
  - ``ruff`` E999 is report-only in CI (issue #2194) and advisory in the hooks
    (issue #2592), and its per-file-ignores exempt the generated
    ``src/copilot-cli`` mirror trees, so it would not block this regardless.
  - ``pytest`` only fails on a ``SyntaxError`` when a collected test imports the
    broken module; nothing imports these utility modules.

The fix is to validate syntax against the *minimum supported* Python version,
not the dev target. ``ast.parse(..., feature_version=floor)`` re-parses with the
floor grammar from any host interpreter (CI's 3.14 included) and rejects syntax
that is newer than the floor, catching PEP 758 misuse and classic syntax errors
alike. This is deliberately separate from the ruff style backlog: a file that
does not parse at the floor is a zero-false-positive defect, so it blocks now.

See ``decision-python-floor-syntax-gate`` (Serena memory) for the reasoning.

Exit codes (ADR-035):
    0 - Success (every file parses at the floor)
    1 - Logic error (one or more files failed to parse at the floor)
    2 - Config error (invalid repository root)
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

# Fallback floor if pyproject.toml cannot be read. Matches the documented
# `requires-python = ">=3.10"` contract at the time of writing (issue #2655).
_DEFAULT_FLOOR = (3, 10)

# Directories never worth parsing: virtualenvs, VCS metadata, caches, vendored
# node deps. Only consulted by the filesystem-walk fallback; the primary path
# uses `git ls-files`, which already excludes untracked trees.
_SKIP_DIRS = frozenset(
    {".venv", "venv", ".git", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache"}
)

_REQUIRES_PYTHON_RE = re.compile(r"""requires-python\s*=\s*["'][^"']*?>=\s*(\d+)\.(\d+)""")


def support_floor(repo_root: Path) -> tuple[int, int]:
    """Return the (major, minor) floor from pyproject's ``requires-python``.

    Parsed with a regex rather than ``tomllib`` so the gate itself runs on the
    floor interpreter (3.10), where ``tomllib`` is absent. Falls back to
    ``_DEFAULT_FLOOR`` when the field is missing or unparseable.
    """
    pyproject = repo_root / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return _DEFAULT_FLOOR
    match = _REQUIRES_PYTHON_RE.search(text)
    if not match:
        return _DEFAULT_FLOOR
    return (int(match.group(1)), int(match.group(2)))


def _tracked_python_files(repo_root: Path) -> list[Path]:
    """Return tracked ``*.py`` files via ``git ls-files``; walk on failure.

    ``git ls-files`` lists committed and staged files, which is exactly the set
    a PR ships. CI checks out the branch (PR files are tracked) and local
    pre-PR runs see staged work, so the gate covers what is about to merge.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "*.py"],
            capture_output=True,
            text=True,
            check=True,
        )
        rels = [line for line in completed.stdout.splitlines() if line.strip()]
        return [repo_root / rel for rel in rels]
    except (OSError, subprocess.SubprocessError):
        return _walk_python_files(repo_root)


def _walk_python_files(repo_root: Path) -> list[Path]:
    """Fallback discovery when git is unavailable: walk excluding ``_SKIP_DIRS``."""
    found: list[Path] = []
    for path in repo_root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.relative_to(repo_root).parts):
            continue
        found.append(path)
    return found


def find_syntax_errors(repo_root: Path, floor: tuple[int, int] | None = None) -> list[tuple[Path, str]]:
    """Parse every tracked file at ``floor``; return ``(path, message)`` failures."""
    if floor is None:
        floor = support_floor(repo_root)
    failures: list[tuple[Path, str]] = []
    for path in _tracked_python_files(repo_root):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            failures.append((path, f"read error: {exc}"))
            continue
        try:
            ast.parse(source, filename=str(path), feature_version=floor)
        except SyntaxError as exc:
            failures.append((path, f"{exc.msg} (line {exc.lineno})"))
    return failures


def validate_python_syntax(repo_root: Path) -> bool:
    """Return True when every tracked file parses at the support floor.

    Runner-facing entry point matching the ``validate_*(repo_root) -> bool``
    contract used by ``pre_pr.py``.
    """
    floor = support_floor(repo_root)
    failures = find_syntax_errors(repo_root, floor)
    if not failures:
        return True
    floor_str = f"{floor[0]}.{floor[1]}"
    print(
        f"[FAIL] {len(failures)} Python file(s) failed to parse at the support "
        f"floor (Python {floor_str}):",
        file=sys.stderr,
    )
    for path, message in failures:
        rel = path.relative_to(repo_root) if path.is_relative_to(repo_root) else path
        print(f"  {rel}: {message}", file=sys.stderr)
    print(
        f"\nFix: use only syntax valid in Python {floor_str}+. Plugin hooks run "
        "under the host interpreter, which may be older than the 3.14 dev target; "
        "PEP 758 unparenthesized except clauses and other 3.14-only syntax wedge "
        "the CLI on older hosts (issue #2655).",
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
    return 0 if validate_python_syntax(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
