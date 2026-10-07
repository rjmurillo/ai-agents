#!/usr/bin/env python3
"""Fail CI on mypy errors that land on lines this change added or modified.

``pyproject.toml`` configures mypy, and two local gates run it: the pre-push
lefthook job and ``pre_pr.py`` (``checks_mypy.py``). No workflow ran either, so
a push from a clone without ``lefthook install``, the web editor, or the API
merged type errors with nothing on the remote to catch them. A gate that only
fires locally is not a gate.

This script is the remote copy of the pre-push gate, not a second
implementation. It reuses ``git_hook_policy.run_mypy``, which owns the
diff-line ratchet (issue #2993): pre-existing errors stay visible in the log,
and only an error on an added or modified line blocks. Changed-file discovery
reuses ``ruff_ratchet.changed_python_files`` so both CI ratchets agree on scope
and on the fallback when the requested base ref is stale.

Fail-closed behavior comes from ``run_mypy``: an unresolvable diff base, or a
mypy exit with no parseable error line (a crash), blocks.

Exit codes (AGENTS.md contract):
    0 - ok (no changed Python files, or no errors on changed lines)
    1 - a mypy error sits on an added or modified line
    2 - config error (repo root is not a git worktree, unsafe path)
    3 - external error (git could not list the changed files)
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.ruff_ratchet import changed_python_files
from scripts.validation.git_hook_policy import (
    MYPY_RATCHET_BASE_REF_ENV,
    run_mypy,
)

EXIT_OK = 0
EXIT_CONFIG = 2
_FALLBACK_BASE_REF = "origin/main"


def default_base_ref() -> str:
    """Return the diff base from the environment, matching the ruff ratchet.

    A push event compares against ``origin/main`` so a feature branch is judged
    on everything it ships, not only on its last push. A zero SHA (the
    ``before`` of a new branch) also falls back.
    """
    if os.environ.get("GITHUB_EVENT_NAME") == "push":
        return _FALLBACK_BASE_REF
    raw_base_ref = os.environ.get(MYPY_RATCHET_BASE_REF_ENV, "").strip()
    if raw_base_ref and raw_base_ref.strip("0"):
        return raw_base_ref
    return _FALLBACK_BASE_REF


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run mypy on changed Python files; block on errors in changed lines."
    )
    parser.add_argument(
        "--base-ref",
        default=default_base_ref(),
        help=f"Git ref used as the diff base (default: {MYPY_RATCHET_BASE_REF_ENV} "
        "or origin/main).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: current working directory).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = args.repo_root.resolve()
    if not (repo_root / ".git").exists():
        print(f"error: {repo_root} is not a git worktree", file=sys.stderr)
        return EXIT_CONFIG

    status, files, resolved_base_ref = changed_python_files(args.base_ref, repo_root)
    if status != EXIT_OK:
        return status
    if not files:
        print(f"Mypy ratchet passed: 0 Python files changed against {resolved_base_ref}.")
        return EXIT_OK

    # run_mypy reads its diff base from this variable. Pin it to the ref that
    # produced the file list, so a stale requested ref cannot drop the line map
    # to None and block on every pre-existing error in every changed file.
    os.environ[MYPY_RATCHET_BASE_REF_ENV] = resolved_base_ref
    print(f"Type-checking {len(files)} changed Python file(s) against {resolved_base_ref}...")
    exit_code = run_mypy(files, repo_root)
    if exit_code == EXIT_OK:
        print(
            f"Mypy ratchet passed for {len(files)} changed Python file(s): "
            "no errors on added or modified lines."
        )
    else:
        print(
            f"Mypy ratchet failed (exit {exit_code}): see the errors above on lines "
            "this change added or modified.",
            file=sys.stderr,
        )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
