#!/usr/bin/env python3
"""Commit and push a fixed set of paths when the working tree is dirty.

Replaces the inline shell block used by bot-authored maintenance workflows,
which configured a committer identity, tested `git status --porcelain` for
output, then staged, committed, and pushed. Keeping the branch here (ADR-006:
no logic in YAML) makes the dirty check and the no-op path testable.

The caller passes the paths to stage explicitly; this script never stages the
whole tree. `git status --porcelain` is evaluated against those paths only, so
an unrelated dirty file cannot trigger a commit that would then stage nothing.

Authentication is the caller's job (`gh auth setup-git` before this step). This
script only configures the committer identity for the local repository.

EXIT CODES (ADR-035):
  0  - Success: committed and pushed, or nothing to commit
  1  - Error: a git command failed
  2  - Error: usage/configuration (git binary missing)
"""

from __future__ import annotations

import argparse
import subprocess
import sys

EXIT_SUCCESS = 0
EXIT_GIT_FAILED = 1
EXIT_USAGE = 2


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a git command, capturing combined output as UTF-8 text."""
    return subprocess.run(
        ["git", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _run(args: list[str]) -> int:
    """Run a git command and report failures. Returns the git exit code."""
    result = _git(args)
    if result.returncode != 0:
        print(f"ERROR: git {' '.join(args)} failed:", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
    return result.returncode


def dirty(paths: list[str]) -> bool:
    """Return True when `git status --porcelain` reports changes under paths."""
    result = _git(["status", "--porcelain", "--", *paths])
    if result.returncode != 0:
        raise RuntimeError(result.stdout)
    return bool(result.stdout.strip())


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the commit-and-push helper."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        action="append",
        required=True,
        help="Path to stage and watch for changes. Repeatable.",
    )
    parser.add_argument(
        "--message",
        action="append",
        required=True,
        help="Commit message paragraph, in order. Repeatable (maps to git -m).",
    )
    parser.add_argument("--user-name", required=True, help="git user.name to set.")
    parser.add_argument("--user-email", required=True, help="git user.email to set.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Commit and push the given paths when dirty. Returns an ADR-035 code."""
    args = build_parser().parse_args(argv)

    try:
        for key, value in (("user.name", args.user_name), ("user.email", args.user_email)):
            if _run(["config", key, value]) != 0:
                return EXIT_GIT_FAILED

        if not dirty(args.path):
            print("No changes to commit")
            return EXIT_SUCCESS

        messages: list[str] = []
        for message in args.message:
            messages.extend(["-m", message])

        staged = ["add", "--", *args.path]
        for command in (staged, ["commit", *messages], ["push"]):
            if _run(command) != 0:
                return EXIT_GIT_FAILED
    except FileNotFoundError as exc:
        print(f"ERROR: git not available: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except RuntimeError as exc:
        print(f"ERROR: git status failed: {exc}", file=sys.stderr)
        return EXIT_GIT_FAILED

    print("Changes committed and pushed")
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
