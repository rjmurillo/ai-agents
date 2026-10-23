#!/usr/bin/env python3
"""Blocking gate: every tracked Python file must parse at the support floor.

Root cause this prevents (issue #2655, regressed by PR #2640): code shipped to
``main`` using ``except OSError, ValueError:`` (unparenthesized ``except``
tuples). This is PEP 758 syntax,
which Python 3.14 accepts but 3.13 and earlier reject as a ``SyntaxError``. The
Copilot CLI runs plugin hooks under the host's ambient interpreter (``py -3`` /
``python3``); on a machine where that resolved to 3.13 the PreToolUse dispatcher
hit the ``SyntaxError`` at import, failed closed, and denied every tool call.

Why no existing gate caught it:

  - The dev and CI target is Python 3.14 (``[tool.ruff] target-version=py314``,
    the pytest workflow runs 3.14). On 3.14 the code is *valid*, so it compiles,
    imports, and tests pass. The defect only appears under the hook-execution
    portability floor: the oldest interpreter a Copilot CLI host may resolve
    ``python3`` / ``py -3`` to. That floor is a property of the deployment
    target, not of the ``requires-python`` install contract, which may
    legitimately be higher (issue #3008 raised it to 3.14 for the dev package).
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
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

# Hook-execution portability floor: the oldest Python a Copilot CLI host may run
# plugin hooks under. Deliberately INDEPENDENT of `requires-python` in
# pyproject.toml (the dev/install contract, which is higher since issue #3008).
# Raising this drops support for older hosts and must be a conscious decision;
# tests/validation/test_validate_python_syntax.py::test_pep758_rejected_at_floor
# guards it. See issue #2655 (why the gate exists) and issue #3008 (why the gate
# floor decoupled from requires-python).
_SUPPORT_FLOOR = (3, 10)

# Directories never worth parsing: virtualenvs, VCS metadata, caches, vendored
# node deps. Only consulted by the filesystem-walk fallback; the primary path
# uses `git ls-files`, which already excludes untracked trees.
_SKIP_DIRS = frozenset(
    {".venv", "venv", ".git", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache"}
)


def support_floor() -> tuple[int, int]:
    """Return the (major, minor) hook-execution portability floor.

    This is the oldest interpreter a Copilot CLI host may run plugin hooks
    under, NOT the ``requires-python`` install contract in ``pyproject.toml``.
    The two were unified while both were 3.10; issue #3008 raised
    ``requires-python`` to 3.14 for the dev/CI package, so the gate pins its own
    floor here to keep protecting older hosts (issue #2655).
    """
    return _SUPPORT_FLOOR


def _tracked_python_files(repo_root: Path) -> list[Path]:
    """Return tracked ``*.py`` files via ``git ls-files``.

    ``git ls-files`` also lists tracked files deleted in an unstaged worktree.
    ``find_syntax_errors`` reads those paths from the index, so an indexed file
    cannot bypass validation when its worktree copy is missing.
    """
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "*.py"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=10,
        )
        rels = [line for line in completed.stdout.splitlines() if line.strip()]
        return [repo_root / rel for rel in rels]
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("git ls-files timed out after 10 seconds") from exc
    except (OSError, subprocess.CalledProcessError):
        return _walk_python_files(repo_root)


def _read_python_source(repo_root: Path, path: Path) -> str:
    """Read worktree content, or indexed content when the worktree file is absent."""
    if path.is_file():
        return path.read_text(encoding="utf-8")
    relative = path.relative_to(repo_root).as_posix()
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "show", f":{relative}"],
        capture_output=True,
        check=True,
        timeout=10,
    )
    return completed.stdout.decode("utf-8")


def _walk_python_files(repo_root: Path) -> list[Path]:
    """Fallback discovery when git is unavailable: walk excluding ``_SKIP_DIRS``."""
    found: list[Path] = []
    for path in repo_root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.relative_to(repo_root).parts):
            continue
        found.append(path)
    return found


# Parsing is CPU bound (about 10 s for 4.5k files, 55 MB of source, on one core;
# issue #6734) and every file is independent, so a large tree fans out across
# worker interpreters. The verdict never depends on the fan-out: every file is
# parsed either way, results are reassembled in discovery order, and any worker
# failure falls back to the serial in-process path, which stays authoritative.
# Below this many files the interpreter start-up costs more than it saves.
_PARALLEL_MIN_FILES = 256
_MAX_WORKERS = 32
_WORKER_TIMEOUT_SECONDS = 300
_WORKER_FLAG = "--parse-worker"


def _parse_message(source: str, filename: str, floor: tuple[int, int]) -> str | None:
    """Return the failure message for ``source`` at ``floor``, or None when it parses."""
    try:
        ast.parse(source, filename=filename, feature_version=floor)
    except SyntaxError as exc:
        return f"{exc.msg} (line {exc.lineno})"
    return None


def _worker_count(item_count: int) -> int:
    """Return how many worker interpreters to use; 1 means stay in-process."""
    if item_count < _PARALLEL_MIN_FILES:
        return 1
    return max(1, min(os.process_cpu_count() or 1, _MAX_WORKERS, item_count))


def _run_parse_worker(payload: str) -> list[str | None]:
    """Run one worker interpreter over a JSON payload; return its messages."""
    completed = subprocess.run(
        [sys.executable, "-I", str(Path(__file__).resolve()), _WORKER_FLAG],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=_WORKER_TIMEOUT_SECONDS,
    )
    messages: list[str | None] = json.loads(completed.stdout)
    return messages


def _parse_in_workers(
    items: list[tuple[str, str]], floor: tuple[int, int], workers: int
) -> list[str | None]:
    """Parse ``items`` across ``workers`` interpreters, preserving item order.

    Items are dealt round-robin so large and small files spread evenly.
    """
    shards = [list(range(offset, len(items), workers)) for offset in range(workers)]
    payloads = [
        json.dumps({"floor": list(floor), "items": [items[i] for i in shard]}) for shard in shards
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        shard_results = list(pool.map(_run_parse_worker, payloads))
    messages: list[str | None] = [None] * len(items)
    for shard, results in zip(shards, shard_results, strict=True):
        if len(results) != len(shard):
            raise ValueError("parse worker returned a different number of results")
        for index, message in zip(shard, results, strict=True):
            messages[index] = message
    return messages


def _parse_all(items: list[tuple[str, str]], floor: tuple[int, int]) -> list[str | None]:
    """Return one failure message (or None) per ``(filename, source)`` item."""
    workers = _worker_count(len(items))
    if workers > 1:
        try:
            return _parse_in_workers(items, floor, workers)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            # Worker start-up, crash, timeout, or malformed output: the serial
            # path below parses the same inputs and decides the verdict.
            pass
    return [_parse_message(source, name, floor) for name, source in items]


def _worker_main() -> int:
    """Worker entry: read a JSON payload on stdin, write one message per item."""
    payload = json.load(sys.stdin)
    floor = (int(payload["floor"][0]), int(payload["floor"][1]))
    messages = [_parse_message(source, name, floor) for name, source in payload["items"]]
    json.dump(messages, sys.stdout)
    return 0


def find_syntax_errors(
    repo_root: Path, floor: tuple[int, int] | None = None
) -> list[tuple[Path, str]]:
    """Parse every tracked file at ``floor``; return ``(path, message)`` failures."""
    if floor is None:
        floor = support_floor()
    failures: list[tuple[Path, str]] = []
    # Failures keep discovery order: read errors and parse errors interleave by
    # file, exactly as the one-file-at-a-time loop reported them.
    slots: list[tuple[Path, str | None]] = []
    items: list[tuple[str, str]] = []
    for path in _tracked_python_files(repo_root):
        try:
            source = _read_python_source(repo_root, path)
        except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
            slots.append((path, f"read error: {exc}"))
            continue
        slots.append((path, None))
        items.append((str(path), source))
    messages = iter(_parse_all(items, floor))
    for path, read_error in slots:
        message = read_error if read_error is not None else next(messages)
        if message is not None:
            failures.append((path, message))
    return failures


def validate_python_syntax(repo_root: Path) -> bool:
    """Return True when every tracked file parses at the support floor.

    Runner-facing entry point matching the ``validate_*(repo_root) -> bool``
    contract used by ``pre_pr.py``.
    """
    floor = support_floor()
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
    if args == [_WORKER_FLAG]:
        return _worker_main()
    repo_root = Path(args[0]).resolve() if args else Path(__file__).resolve().parents[2]
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    return 0 if validate_python_syntax(repo_root) else 1


if __name__ == "__main__":
    raise SystemExit(main())
