#!/usr/bin/env python3
"""Whole-repo ruff count ratchet: fail only when the total violation count grows.

Issue #2993, regression guard option C. This complements the diff-scoped
``scripts/ci/ruff_ratchet.py`` (which lints only the changed files and so lets a
contributor inherit latent debt the moment they touch a shared file). This gate
freezes the whole-repo violation ceiling in ``ruff_count_baseline.txt``. The
count must not exceed that ceiling. Unrecorded improvements pass so parallel
cleanup PRs do not all rewrite the same baseline line.

Scope is git-TRACKED Python files, not a directory walk. ``ruff check .`` also
walks untracked scratch, nested git worktrees, and vendored caches that a
contributor happens to have on disk (``pr3097-worktree/``, ``.cache/worktrees/``),
which inflated a local run to 767 against a real tracked count of 361 and made
the gate report a phantom regression outside CI. Tracked files are the only
thing a PR can change, so they are the only thing the baseline should freeze.

Stdlib only: this runs by path in CI (``python scripts/ci/ruff_count_ratchet.py``)
and must not depend on the project's import graph.

Exit codes (AGENTS.md contract):
    0 - ok (count <= baseline, or --update records a decrease)
    1 - regression (count > baseline, or baseline raised vs --base-ref)
    2 - config error (baseline missing or malformed, bad args)
    3 - external error (ruff could not run)
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.count_ratchet import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    EXIT_REGRESSION,
    build_parser,
    chunk,
    git_environment,
    run,
    tracked_files,
)

__all__ = [
    "EXIT_CONFIG",
    "EXIT_EXTERNAL",
    "EXIT_OK",
    "EXIT_REGRESSION",
    "MERGE_TREE_BACKED",
    "current_count",
    "main",
]

_BASELINE_PATH = Path(__file__).with_name("ruff_count_baseline.txt")

MERGE_TREE_BACKED = True
"""This baseline is registered in ``merge_tree_ratchet_registry.py::RATCHETS``.

Registration is what lets ``count_ratchet.run`` pass a branch that merely holds
a number ``main`` lowered underneath it: the merged result is measured by
``scripts/ci/merge_tree_ratchet_check.py`` instead. Pinned against the registry
by ``tests/ci/test_merge_tree_backing_declarations.py``. The local
``count-ratchets`` aggregate and CI merge-tree step both run without path
filters, so registry membership is the complete backstop eligibility
invariant.
"""

# Every extension ruff lints. Kept in lockstep with the workflow paths filter.
_SCAN_GLOBS = ("*.py", "*.pyi", "*.ipynb")

# ruff reports file-access failures as an ordinary E902 diagnostic on exit 1.
# Counting those as lint debt turns a deleted-but-tracked file or an unreadable
# path into a phantom count change, so they are treated as an environment
# failure instead.
_IO_ERROR_CODE = "E902"


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
    files = tracked_files(repo_root, _SCAN_GLOBS)
    if files is None:
        return None
    if not files:
        return 0

    total = 0
    for batch in chunk(files):
        try:
            proc = subprocess.run(
                ["ruff", "check", "--output-format", "json-lines", "--", *batch],
                cwd=repo_root,
                capture_output=True,
                text=True,
                errors="replace",
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

    Runs under ``git_environment()`` for the reason recorded there: an exported
    ``GIT_DIR`` outranks ``-C <root>``, so a push from a linked worktree would
    resolve ``ref`` in the pushing worktree rather than in ``repo_root``
    (issue #4914).
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
            errors="replace",
            encoding="utf-8",
            check=False,
            env=git_environment(),
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(
        "Whole-repo ruff violation-count ratchet (issue #2993).", _BASELINE_PATH
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return run(
        args,
        label="ruff count ratchet",
        counter=current_count,
        scan_error="ruff failed to run",
        regression_advice=(
            "New ruff violations cannot merge; fix them or, if they are "
            "unavoidable, coordinate a baseline change (issue #2993)."
        ),
        merge_tree_backed=MERGE_TREE_BACKED,
    )


if __name__ == "__main__":
    sys.exit(main())
