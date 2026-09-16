"""Validate gate_latency.py's arguments into the values a measurement needs.

Split from ``scripts/metrics/gate_latency.py`` so the entry point holds one
concern. That file parses argv and returns an exit code; this one turns the
parsed namespace into a repository path, a change-class file list, and a
lefthook command, or into the exit code that says why it cannot.

Every function here returns either its value or an ``int`` exit code, never
raises for an invalid input, because the exit-code contract is the module's
whole purpose: 2 for a configuration problem discovered before any hook runs.

The split answers a cohesion finding from this repository's own
``code-qualities-assessment`` axis, which gates a new file below its
thresholds with exit 11.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from scripts.metrics.gate_latency_classes import (
    get_change_class_files,
    missing_change_class_paths,
)
from scripts.metrics.gate_latency_probe import _load_lefthook_config, _resolve_lefthook_command


def _validate_repo_and_repetitions(args: argparse.Namespace) -> tuple[Path, int] | int:
    """Guard clauses that need no file I/O beyond ``repo`` itself (AC-07 exit-2)."""
    repo = Path(args.repo).resolve()
    if not repo.is_dir() or not (repo / ".git").exists():
        print(f"error: not a git repository: {repo}", file=sys.stderr)
        return 2
    if args.repetitions < 1:
        print(f"error: --repetitions must be >= 1, got {args.repetitions}", file=sys.stderr)
        return 2
    return repo, args.repetitions


def _validate_hook(repo: Path, hook: str) -> dict[str, Any] | int:
    """Load ``lefthook.yml`` and confirm ``hook`` names a real hook (AC-07 exit-2)."""
    config = _load_lefthook_config(repo)
    if config is None:
        print("error: missing or invalid lefthook.yml", file=sys.stderr)
        return 2
    hook_cfg = config.get(hook)
    if not isinstance(hook_cfg, dict) or "jobs" not in hook_cfg:
        print(f"error: unknown hook: {hook}", file=sys.stderr)
        return 2
    return config


def _validate_change_class(repo: Path, change_class: str) -> tuple[str, ...] | int:
    """Resolve ``change_class`` to its file list and confirm every path exists (AC-08)."""
    files = get_change_class_files(change_class)
    if files is None:
        print(f"error: unknown change class: {change_class}", file=sys.stderr)
        return 2
    missing = missing_change_class_paths(repo, files)
    if missing:
        print(
            f"error: change class {change_class!r} names a missing path: {missing[0]}",
            file=sys.stderr,
        )
        return 2
    return files


def _resolve_inputs(args: argparse.Namespace) -> tuple[Path, tuple[str, ...], list[str]] | int:
    """Run every exit-2 guard clause and resolve what a repetition needs to run.

    Returns the exit code to use on the first failure, or ``(repo, files,
    lefthook_cmd)`` once every AC-07 exit-2 condition has cleared. The
    exit-1 dirty-tree check stays in ``main``: it needs the resolved
    ``repo`` from here first, and it is a different exit code (AC-07)
    reported for a different reason (a tree state, not a configuration
    problem).
    """
    resolved = _validate_repo_and_repetitions(args)
    if isinstance(resolved, int):
        return resolved
    repo, _repetitions = resolved

    hook_result = _validate_hook(repo, args.hook)
    if isinstance(hook_result, int):
        return hook_result

    files = _validate_change_class(repo, args.change_class)
    if isinstance(files, int):
        return files

    lefthook_cmd = _resolve_lefthook_command(repo, args.lefthook_bin)
    if lefthook_cmd is None:
        print("error: lefthook binary not found", file=sys.stderr)
        return 2

    return repo, files, lefthook_cmd
