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

Speed (issue #6734): the visitor skips expression subtrees, because Python
allows a ``def`` only as a statement. Trees of ``_PARALLEL_MIN_FILES`` or more
files are scanned in child interpreters. Every file is still parsed, and the
findings and their order match a serial scan.

Exit codes (ADR-035):
    0 - Success (no nested test functions found)
    1 - Logic error (one or more uncollectable test functions found)
    2 - Config error (invalid repository root)
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_SKIP_DIRS = frozenset(
    {".venv", "venv", ".git", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache"}
)


# Below this many files the worker start-up cost outweighs the saving, so the
# scan stays in-process. The repository's own tree is well above it.
_PARALLEL_MIN_FILES = 128
_MAX_WORKERS = 8
_WORKER_TIMEOUT_SECONDS = 120

# The child loads this file by path instead of putting scripts/validation on
# sys.path, so a sibling module named like a stdlib module cannot shadow it.
_WORKER_BOOTSTRAP = (
    "import importlib.util as u, sys; "
    "spec = u.spec_from_file_location('check_nested_tests_worker', sys.argv[1]); "
    "module = u.module_from_spec(spec); spec.loader.exec_module(module); "
    "raise SystemExit(module._worker_main())"
)


class _NestedTestFinder(ast.NodeVisitor):
    """Walk an AST and record ``test_*`` functions nested inside functions.

    Expression subtrees are skipped: Python grammar allows a ``def`` only as a
    statement, so no function definition can sit under an ``ast.expr`` node. The
    skip removes most of the visited nodes without changing any verdict.
    """

    def __init__(self) -> None:
        self.findings: list[tuple[int, str]] = []
        self._func_depth = 0

    def generic_visit(self, node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, ast.expr):
                self.visit(child)

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


def _scan_file(path: Path) -> list[tuple[int, str]] | None:
    """Return the nested ``test_*`` findings in one file, or None when skipped.

    A file that is not a regular file, cannot be read as UTF-8, or does not
    parse is skipped, exactly as the gate has always done.
    """
    if not path.is_file():
        return None
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return None
    finder = _NestedTestFinder()
    finder.visit(tree)
    return finder.findings


def _scan_serial(paths: list[Path]) -> list[list[tuple[int, str]] | None]:
    return [_scan_file(path) for path in paths]


def _worker_count(file_count: int) -> int:
    try:
        available = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        available = os.cpu_count() or 1
    return max(1, min(available, _MAX_WORKERS, file_count))


def _scan_chunk_in_worker(paths: list[Path]) -> list[list[tuple[int, str]] | None]:
    """Scan ``paths`` in a child interpreter; fall back to in-process on any failure.

    The fallback re-runs the unmodified serial scan, so a worker that crashes,
    times out, or returns malformed output yields the same result and the same
    exceptions the serial gate would have produced. It also prints one
    ``[WARN]`` line, so a dead worker path shows up as a warning instead of a
    silent slowdown.
    """
    reason = "unknown"
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _WORKER_BOOTSTRAP, str(Path(__file__).resolve())],
            input=json.dumps([str(path) for path in paths]),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=_WORKER_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            reason = f"exit code {completed.returncode}"
        else:
            decoded = json.loads(completed.stdout)
            if isinstance(decoded, list) and len(decoded) == len(paths):
                parsed = [
                    None if entry is None else [(int(line), str(name)) for line, name in entry]
                    for entry in decoded
                ]
                if completed.stderr:
                    # Keep parser warnings (for example SyntaxWarning) visible,
                    # as they are when the scan runs in-process.
                    sys.stderr.write(completed.stderr)
                return parsed
            reason = "malformed result"
    except (OSError, subprocess.SubprocessError, ValueError, TypeError) as error:
        reason = f"{type(error).__name__}: {error}"
    print(
        f"[WARN] nested-test scan worker failed ({reason}); "
        f"scanning {len(paths)} file(s) in-process",
        file=sys.stderr,
    )
    return _scan_serial(paths)


def _scan_parallel(paths: list[Path], workers: int) -> list[list[tuple[int, str]] | None]:
    """Scan ``paths`` across ``workers`` child interpreters, keeping input order."""
    slices = [list(range(index, len(paths), workers)) for index in range(workers)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        chunk_results = list(
            pool.map(lambda indices: _scan_chunk_in_worker([paths[i] for i in indices]), slices)
        )
    ordered: list[list[tuple[int, str]] | None] = [None] * len(paths)
    for indices, chunk in zip(slices, chunk_results, strict=True):
        for index, result in zip(indices, chunk, strict=True):
            ordered[index] = result
    return ordered


def _worker_main() -> int:
    """Child entry point: read a JSON path list on stdin, write findings as JSON."""
    paths = [Path(raw) for raw in json.load(sys.stdin)]
    json.dump(_scan_serial(paths), sys.stdout)
    return 0


def find_nested_tests(
    repo_root: Path, *, workers: int | None = None
) -> list[tuple[Path, int, str]]:
    """Return ``(path, lineno, func_name)`` for every uncollectable test function.

    A test function is uncollectable when it is defined inside the body of
    another function. Nested classes (``ClassDef`` enclosing ``test_*``) are
    NOT flagged because pytest collects them.

    Every tracked file is scanned. Large trees are split across child
    interpreters; the findings and their order match a serial scan. ``workers``
    overrides the automatic worker count (1 forces the in-process scan).
    """
    paths = _tracked_test_files(repo_root)
    if workers is None:
        count = _worker_count(len(paths)) if len(paths) >= _PARALLEL_MIN_FILES else 1
    else:
        count = max(1, min(workers, len(paths)))
    per_file = _scan_parallel(paths, count) if count > 1 else _scan_serial(paths)
    return [
        (path, lineno, name)
        for path, findings in zip(paths, per_file, strict=True)
        for lineno, name in (findings or [])
    ]


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
