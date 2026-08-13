#!/usr/bin/env python3
"""Fail on ruff violations in changed Python files only."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

_ZERO_SHA = re.compile(r"^0+$")
_FALLBACK_BASE_REF = "origin/main"


def default_base_ref() -> str:
    if os.environ.get("GITHUB_EVENT_NAME") == "push":
        return _FALLBACK_BASE_REF

    raw_base_ref = os.environ.get("RUFF_RATCHET_BASE_REF", "").strip()
    if raw_base_ref and _ZERO_SHA.fullmatch(raw_base_ref) is None:
        return raw_base_ref
    return _FALLBACK_BASE_REF


def git_diff_name_only(base_ref: str, repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{base_ref}...HEAD",
        ],
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
    )


def changed_python_files(base_ref: str, repo_root: Path) -> tuple[int, list[str]]:
    result = git_diff_name_only(base_ref, repo_root)
    if result.returncode != 0 and base_ref != _FALLBACK_BASE_REF:
        result = git_diff_name_only(_FALLBACK_BASE_REF, repo_root)
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        return EXIT_EXTERNAL, []

    files = [
        line
        for line in result.stdout.splitlines()
        if line.endswith(".py") and (repo_root / line).is_file()
    ]
    return EXIT_OK, files


def run_ruff(files: Sequence[str], repo_root: Path) -> int:
    if not files:
        print("No changed Python files found. Ruff ratchet passed.")
        return EXIT_OK

    result = subprocess.run(
        ["ruff", "check", "--output-format=github", "--", *files],
        check=False,
        capture_output=True,
        cwd=repo_root,
        text=True,
        errors="replace",
        encoding="utf-8",
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")

    if result.returncode == 0:
        print(f"Ruff ratchet passed for {len(files)} changed Python file(s).")
        return EXIT_OK
    if result.returncode == 1:
        print(f"Ruff ratchet failed for {len(files)} changed Python file(s).", file=sys.stderr)
        return EXIT_VIOLATIONS
    return EXIT_EXTERNAL


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ruff only on Python files changed since a base ref."
    )
    parser.add_argument(
        "--base-ref",
        default=default_base_ref(),
        help="Git ref used as the diff base (default: RUFF_RATCHET_BASE_REF or origin/main).",
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

    status, files = changed_python_files(args.base_ref, repo_root)
    if status != EXIT_OK:
        return status
    return run_ruff(files, repo_root)


if __name__ == "__main__":
    sys.exit(main())
