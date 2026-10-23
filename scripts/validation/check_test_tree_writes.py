#!/usr/bin/env python3
"""Gate: detect test files that write to the repository working tree.

A test that creates files or directories under the project root (outside
``tmp_path`` or a sanctioned gitignored scratch root) leaves litter after
every run. The litter makes ``git status`` unreliable, inflates repo-wide
scanner baselines, and turns ``git add`` risky.

Four confirmed instances were fixed in PR #3688 (issue #3772). This gate
prevents a fifth by statically scanning test files for write patterns rooted
at the repo root.

Detection strategy
------------------
Walk every ``test_*.py`` file and look for call nodes whose callee is a
known write operation (``open``, ``Path.write_text``, ``Path.write_bytes``,
``Path.mkdir``, ``Path.touch``, ``shutil.copy``, ``shutil.copyfile``,
``shutil.copytree``, ``shutil.rmtree``, ``shutil.move``).  If the first
argument to the call is an attribute access on a name that matches a known
project-root binding (``_PROJECT_ROOT``, ``REPO_ROOT``, ``PROJECT_ROOT``,
``ROOT``, ``_REPO_ROOT``), and the path does NOT pass through ``tmp_path``,
``tmp_dir``, ``tmpdir``, ``tempfile``, ``TemporaryDirectory``, or the
sanctioned ``.pytest_tmp`` scratch root, flag it.

This is an AST-level heuristic. False positives are possible for projects
that intentionally write to the repo root (e.g., changelog generators).
Those should use ``tmp_path`` or a gitignored directory and document why.

Speed (issue #6734)
-------------------
Parsing dominated the run (about 8s of 8.4s over 2034 files). A lexical
prefilter skips files that cannot contain a finding, and large batches scan
in worker interpreters. Neither changes the verdict: the prefilter only skips
ASCII files missing a root-binding or write-operation token, and any worker
failure falls back to the serial scan.

Exit codes (ADR-035):
    0 - Success (no suspect writes found)
    1 - Logic error (one or more suspect writes found)
    2 - Config error (invalid repository root)
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_SKIP_DIRS = frozenset(
    {".venv", "venv", ".git", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache"}
)

# Names that typically hold a reference to the repo / project root.
_ROOT_BINDINGS = frozenset({"_PROJECT_ROOT", "REPO_ROOT", "PROJECT_ROOT", "ROOT", "_REPO_ROOT"})

# Sanctioned scratch roots under the repo tree (gitignored).
_SANCTIONED_SUFFIXES = (".pytest_tmp",)

# Write operations that create / overwrite files on disk.
_WRITE_METHODS = frozenset(
    {
        "write_text",
        "write_bytes",
        "mkdir",
        "touch",
        "open",
    }
)
_SHUTIL_WRITE_FUNCS = frozenset(
    {
        "copy",
        "copyfile",
        "copytree",
        "rmtree",
        "move",
    }
)

# Fixtures / helpers that route to a temp directory - not flagged.
_TEMP_NAMES = frozenset(
    {"tmp_path", "tmp_dir", "tmpdir", "tempfile", "TemporaryDirectory", "mkdtemp", "mkstemp"}
)


class _WriteDetector(ast.NodeVisitor):
    """Visit a module AST and collect (lineno, description) tuples."""

    def __init__(self) -> None:
        self.findings: list[tuple[int, str]] = []

    # ------------------------------------------------------------------ #
    # helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _names_in(node: ast.expr) -> set[str]:
        """Return all Name ids reachable from *node*."""
        return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}

    @staticmethod
    def _is_sanctioned(node: ast.expr) -> bool:
        """True if *node* references a sanctioned scratch root."""
        src = ast.unparse(node)
        return any(s in src for s in _SANCTIONED_SUFFIXES)

    @staticmethod
    def _is_temp_routed(node: ast.expr) -> bool:
        """True if *node* routes through a tmp_path-style fixture."""
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        return bool(names & _TEMP_NAMES)

    def _is_root_rooted(self, node: ast.expr) -> bool:
        """True if *node* is built on a project-root binding."""
        names = self._names_in(node)
        return bool(names & _ROOT_BINDINGS)

    # ------------------------------------------------------------------ #
    # visitors                                                             #
    # ------------------------------------------------------------------ #

    def visit_Call(self, node: ast.Call) -> None:
        self._check_call(node)
        self.generic_visit(node)

    def _check_call(self, node: ast.Call) -> None:
        callee = node.func
        if isinstance(callee, ast.Attribute) and callee.attr in _WRITE_METHODS:
            self._check_method_write(node, callee)
        elif isinstance(callee, ast.Name) and callee.id == "open" and node.args:
            self._check_open_write(node)
        elif (
            isinstance(callee, ast.Attribute)
            and callee.attr in _SHUTIL_WRITE_FUNCS
            and isinstance(callee.value, ast.Name)
            and callee.value.id == "shutil"
            and node.args
        ):
            self._check_shutil_write(node, callee)

    def _check_method_write(self, node: ast.Call, callee: ast.Attribute) -> None:
        """Flag path.write_text() / mkdir() / touch() on a project-root object."""
        obj = callee.value
        if (
            self._is_root_rooted(obj)
            and not self._is_temp_routed(obj)
            and not self._is_sanctioned(obj)
        ):
            self.findings.append(
                (node.lineno, f"write via .{callee.attr}() on project-root-rooted path")
            )

    def _check_open_write(self, node: ast.Call) -> None:
        """Flag open(ROOT / ..., 'w') calls."""
        first_arg = node.args[0]
        if (
            not self._is_root_rooted(first_arg)
            or self._is_temp_routed(first_arg)
            or self._is_sanctioned(first_arg)
        ):
            return
        mode = self._extract_open_mode(node)
        if any(c in mode for c in "wax"):
            self.findings.append((node.lineno, "open() for writing on project-root-rooted path"))

    @staticmethod
    def _extract_open_mode(node: ast.Call) -> str:
        mode = ""
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            mode = str(node.args[1].value)
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = str(kw.value.value)
        return mode

    def _check_shutil_write(self, node: ast.Call, callee: ast.Attribute) -> None:
        """Flag shutil operations that write to a project-root destination."""
        dest_args = node.args[:1] if callee.attr == "rmtree" else node.args[1:2]
        for arg in dest_args:
            if (
                self._is_root_rooted(arg)
                and not self._is_temp_routed(arg)
                and not self._is_sanctioned(arg)
            ):
                self.findings.append(
                    (node.lineno, f"shutil.{callee.attr}() writes to project-root-rooted path")
                )
                break


# --------------------------------------------------------------------------- #
# file-level scanner                                                           #
# --------------------------------------------------------------------------- #


# Cheap lexical prefilter. A finding needs a Name node holding a project-root
# binding and a Call whose callee names a write operation. Every identifier in
# an ASCII source file appears verbatim in its text, so a file missing either
# token cannot produce a finding and the parse can be skipped. Non-ASCII
# sources always parse: the parser NFKC-normalizes identifiers, so ``ＲＯＯＴ``
# is the Name ``ROOT`` without containing that text. Both patterns derive from
# the detector constants above so the two cannot drift apart.
_ROOT_TOKEN_RE = re.compile(r"\b(?:" + "|".join(sorted(_ROOT_BINDINGS)) + r")\b")
_WRITE_TOKEN_RE = re.compile(
    r"\b(?:" + "|".join(sorted(_WRITE_METHODS | _SHUTIL_WRITE_FUNCS)) + r")\b"
)


def _may_have_findings(source: str) -> bool:
    """False only when *source* provably cannot contain a finding."""
    if not source.isascii():
        return True
    return bool(_ROOT_TOKEN_RE.search(source) and _WRITE_TOKEN_RE.search(source))


def _scan_source(source: str, filename: str) -> list[tuple[int, str]]:
    """Return (lineno, description) findings for *source*."""
    if not _may_have_findings(source):
        return []

    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []

    detector = _WriteDetector()
    detector.visit(tree)
    return detector.findings


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Return (lineno, description) findings for *path*."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    return _scan_source(source, str(path))


# Below this many files, starting worker interpreters costs more than it saves.
_PARALLEL_MIN_FILES = 64
_MAX_WORKERS = 8
_WORKER_TIMEOUT_S = 300
_WORKER_FLAG = "--scan-worker"


def _scan_files(paths: list[Path]) -> list[list[tuple[int, str]]]:
    """Scan *paths* and return one findings list per path, in input order.

    Large batches fan out across worker interpreters. When any worker cannot
    start, fails, or returns a malformed reply, scanning falls back to the
    serial loop, which yields the identical result.
    """
    workers = min(os.cpu_count() or 1, _MAX_WORKERS)
    if len(paths) >= _PARALLEL_MIN_FILES and workers > 1:
        parallel = _scan_files_parallel(paths, workers)
        if parallel is not None:
            return parallel
    return [_scan_file(path) for path in paths]


def _scan_files_parallel(paths: list[Path], workers: int) -> list[list[tuple[int, str]]] | None:
    """Scan *paths* across *workers* interpreters, or return None on any failure."""
    results: list[list[tuple[int, str]]] = [[] for _ in paths]
    procs: list[subprocess.Popen[str]] = []
    try:
        for i in range(workers):
            proc = subprocess.Popen(
                [sys.executable, "-I", str(Path(__file__).resolve()), _WORKER_FLAG],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            procs.append(proc)
            payload = json.dumps([str(p) for p in paths[i::workers]])
            assert proc.stdin is not None
            proc.stdin.write(payload)
            proc.stdin.close()
        for i, proc in enumerate(procs):
            assert proc.stdout is not None
            out, _ = proc.communicate(timeout=_WORKER_TIMEOUT_S)
            if proc.returncode != 0:
                return None
            chunk = [
                [(int(lineno), str(desc)) for lineno, desc in file_findings]
                for file_findings in json.loads(out)
            ]
            if len(chunk) != len(paths[i::workers]):
                return None
            results[i::workers] = chunk
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return None
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    return results


def _run_scan_worker() -> int:
    """Worker mode: read a JSON path list on stdin, write findings JSON on stdout."""
    paths = [Path(p) for p in json.load(sys.stdin)]
    json.dump([_scan_file(p) for p in paths], sys.stdout)
    return 0


def _tracked_test_files(repo_root: Path) -> list[Path]:
    """Return all tracked ``test_*.py`` files under *repo_root*."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    paths = []
    for line in result.stdout.splitlines():
        p = Path(line)
        if p.name.startswith("test_") or p.name.endswith("_test.py"):
            abs_path = repo_root / p
            if abs_path.exists():
                paths.append(abs_path)
    return paths


# --------------------------------------------------------------------------- #
# public API                                                                   #
# --------------------------------------------------------------------------- #


def check_test_tree_writes(repo_root: Path) -> list[tuple[Path, int, str]]:
    """Return (file, lineno, description) for every suspect write found."""
    test_files = _tracked_test_files(repo_root)
    findings: list[tuple[Path, int, str]] = []
    for test_file, file_findings in zip(test_files, _scan_files(test_files), strict=True):
        for lineno, desc in file_findings:
            findings.append((test_file, lineno, desc))
    return findings


def validate_test_tree_writes(repo_root: Path) -> bool:
    """Return True when no test files write to the repository working tree.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract used by
    ``pre_pr_sequence.py``.
    """
    findings = check_test_tree_writes(repo_root)
    if not findings:
        return True
    print(
        f"[FAIL] {len(findings)} test file(s) write to the repository working tree "
        f"instead of tmp_path (issue #3772):",
        file=sys.stderr,
    )
    for path, lineno, desc in findings:
        rel = path.relative_to(repo_root)
        print(f"  {rel}:{lineno}: {desc}", file=sys.stderr)
    return False


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    import argparse

    if argv is None:
        argv = sys.argv[1:]
    if argv == [_WORKER_FLAG]:
        return _run_scan_worker()

    parser = argparse.ArgumentParser(
        description="Detect test files that write to the repository working tree."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root (default: current directory).",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    if not (repo_root / ".git").exists() and not (repo_root / ".git").is_file():
        print(f"error: {repo_root} does not look like a git repository", file=sys.stderr)
        return 2

    findings = check_test_tree_writes(repo_root)
    if not findings:
        print("check_test_tree_writes: OK (no working-tree writes detected)")
        return 0

    print(
        f"check_test_tree_writes: FAIL ({len(findings)} suspect write(s))",
        file=sys.stderr,
    )
    for path, lineno, desc in findings:
        rel = path.relative_to(repo_root)
        print(f"  {rel}:{lineno}: {desc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
