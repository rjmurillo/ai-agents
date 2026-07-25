#!/usr/bin/env python3
"""Whole-repo ruff count ratchet: fail only when the total violation count grows.

Issue #2993, regression guard option C. This complements the diff-scoped
``scripts/ci/ruff_ratchet.py`` (which lints only the changed files and so lets a
contributor inherit latent debt the moment they touch a shared file). This gate
freezes the whole-repo violation total in ``ruff_count_baseline.txt`` and fails a
run only when the count INCREASES. A decrease is allowed and can lower the
baseline with ``--update``, so the pre-existing debt drains monotonically and can
never climb back.

Scope is git-TRACKED Python files, not a directory walk. ``ruff check .`` also
walks untracked scratch, nested git worktrees, and vendored caches that a
contributor happens to have on disk (``pr3097-worktree/``, ``.cache/worktrees/``),
which inflated a local run to 767 against a real tracked count of 361 and made
the gate report a phantom regression outside CI. Tracked files are the only
thing a PR can change, so they are the only thing the baseline should freeze.

Stdlib only: this runs by path in CI (``python scripts/ci/ruff_count_ratchet.py``)
and must not depend on the project's import graph.

Exit codes (AGENTS.md contract):
    0 - ok (count <= baseline)
    1 - regression (count > baseline, or baseline raised vs --base-ref)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (ruff could not run)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

EXIT_OK = 0
EXIT_REGRESSION = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

_BASELINE_PATH = Path(__file__).with_name("ruff_count_baseline.txt")

# Windows CreateProcess caps a command line at 32767 characters. The tracked
# Python set is ~1476 paths / ~70 KB of argv, so the scan is chunked to stay
# under that ceiling on every platform rather than only on POSIX.
_ARGV_BUDGET_BYTES = 24000

# Every extension ruff lints. Kept in lockstep with the workflow paths filter.
_SCAN_GLOBS = ("*.py", "*.pyi", "*.ipynb")

# ruff reports file-access failures as an ordinary E902 diagnostic on exit 1.
# Counting those as lint debt turns a deleted-but-tracked file or an unreadable
# path into a phantom count change, so they are treated as an environment
# failure instead.
_IO_ERROR_CODE = "E902"


def tracked_python_files(repo_root: Path) -> list[str] | None:
    """Git-tracked ruff-lintable paths, or None when git could not run.

    ``.pyi`` and ``.ipynb`` are in scope because ruff lints both. The repo
    tracks none today, so they do not move the baseline, but a PR that adds a
    faulty stub or notebook must not slip past a Python-only gate.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z", "--", *_SCAN_GLOBS],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        sys.stderr.write(f"git could not be launched: {exc}\n")
        return None
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return None
    return [path for path in proc.stdout.split("\0") if path]


def _chunk(paths: Sequence[str], budget: int = _ARGV_BUDGET_BYTES) -> list[list[str]]:
    """Split ``paths`` into batches whose joined length stays under ``budget``."""
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for path in paths:
        cost = len(path) + 1
        if current and size + cost > budget:
            batches.append(current)
            current = []
            size = 0
        current.append(path)
        size += cost
    if current:
        batches.append(current)
    return batches


def _count_diagnostics(stdout: str) -> int | None:
    """Violations in one ruff ``json-lines`` batch, or None on an I/O error.

    A malformed line is counted rather than dropped: the count is the metric
    this gate defends, so an unparseable diagnostic must not silently lower it.
    """
    total = 0
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            total += 1
            continue
        if isinstance(record, dict) and record.get("code") == _IO_ERROR_CODE:
            sys.stderr.write(
                f"ruff could not read {record.get('filename')}: {record.get('message')}\n"
            )
            return None
        total += 1
    return total


def current_count(repo_root: Path) -> int | None:
    """Total tracked-file ruff violations, or None when the scan could not run.

    Uses ``json-lines`` so the count is one violation per output line, robust
    across ruff output-format changes. ruff exits 1 when violations exist and 0
    when clean; both are valid. Any other exit code is an environment failure.
    """
    files = tracked_python_files(repo_root)
    if files is None:
        return None
    if not files:
        return 0

    total = 0
    for batch in _chunk(files):
        try:
            proc = subprocess.run(
                ["ruff", "check", "--output-format", "json-lines", "--", *batch],
                cwd=repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
        except (FileNotFoundError, OSError) as exc:
            sys.stderr.write(f"ruff could not be launched: {exc}\n")
            return None
        if proc.returncode not in (0, 1):
            sys.stderr.write(proc.stderr)
            return None
        batch_count = _count_diagnostics(proc.stdout)
        if batch_count is None:
            return None
        total += batch_count
    return total


def baseline_at_ref(repo_root: Path, ref: str, baseline: Path) -> int | None:
    """Baseline value recorded at ``ref``, or None when it cannot be read.

    Without this the ratchet is one-sided: the gate only fails when the count
    exceeds the baseline, so raising the baseline in the same PR that adds the
    violations passes as an improvement. Comparing against the base branch is
    what makes the baseline monotonic rather than merely advisory.
    """
    try:
        rel = baseline.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        sys.stderr.write(f"baseline {baseline} is outside {repo_root}\n")
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{ref}:{rel}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        sys.stderr.write(f"git could not be launched: {exc}\n")
        return None
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return None
    try:
        return int(proc.stdout.strip())
    except ValueError:
        sys.stderr.write(f"baseline at {ref} is not an integer\n")
        return None


def read_baseline(path: Path) -> int | None:
    """Baseline integer, or None when the file is missing or not an integer."""
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Whole-repo ruff violation-count ratchet (issue #2993)."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=_BASELINE_PATH,
        help="Baseline count file (default: alongside this script).",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Lower the baseline to the current count when the count improved.",
    )
    parser.add_argument(
        "--base-ref",
        help=(
            "Git ref to compare the baseline against. Fails when the working "
            "baseline is higher than the one at this ref, which is what keeps "
            "the ratchet one-directional."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    baseline = read_baseline(args.baseline)
    if baseline is None:
        print(f"error: baseline missing or malformed: {args.baseline}", file=sys.stderr)
        return EXIT_CONFIG

    if args.base_ref:
        base = baseline_at_ref(args.repo_root.resolve(), args.base_ref, args.baseline)
        if base is None:
            print(
                f"error: could not read the baseline at {args.base_ref}",
                file=sys.stderr,
            )
            return EXIT_EXTERNAL
        if baseline > base:
            print(
                f"ruff count ratchet: BASELINE RAISED. {base} -> {baseline} "
                f"(+{baseline - base}) against {args.base_ref}. The baseline may "
                f"only fall. Fix the violations instead of widening the allowance "
                f"(issue #2993).",
                file=sys.stderr,
            )
            return EXIT_REGRESSION

    count = current_count(args.repo_root.resolve())
    if count is None:
        print("error: ruff failed to run", file=sys.stderr)
        return EXIT_EXTERNAL

    if count > baseline:
        print(
            f"ruff count ratchet: REGRESSION. {count} violations > baseline {baseline} "
            f"(+{count - baseline}). New ruff violations cannot merge; fix them or, if "
            f"they are unavoidable, coordinate a baseline change (issue #2993).",
            file=sys.stderr,
        )
        return EXIT_REGRESSION

    if count < baseline:
        message = f"ruff count ratchet: improved {baseline} -> {count} (-{baseline - count})."
        if args.update:
            args.baseline.write_text(f"{count}\n", encoding="utf-8")
            message += " Baseline lowered."
        else:
            message += " Run with --update to lower the baseline."
        print(message)
        return EXIT_OK

    print(f"ruff count ratchet: OK (count == baseline {baseline}).")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
