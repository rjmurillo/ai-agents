#!/usr/bin/env python3
"""Reject commits in a push range whose author/committer matches the placeholder denylist.

Prevents the test@test.com leak pattern (issue #2466) from reaching
origin. Pytest fixtures occasionally write placeholder identities into
git config with the wrong cwd; this guard catches any such commits before
they are pushed.

EXIT CODES (ADR-035):
    0  - All commits in range are clean (or check was skipped)
    1  - One or more commits matched the placeholder denylist
    2  - Config/setup error (bad args, can't read git)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple


def _is_pytest_tmp(repo_root: Path) -> bool:
    """Return True when repo_root is inside pytest's ephemeral tmp_path tree.

    Pytest places tmp_path directories under ``<tempfile.gettempdir()>/pytest-of-*/``
    on most platforms. Commits in such repos are test-generated; blocking them
    would break characterization tests that intentionally plant placeholder
    commits.

    Detection heuristic (conservative):
    - repo_root is under tempfile.gettempdir(), AND
    - any component of the resolved path contains "pytest-of-".

    This heuristic is documented and intentionally conservative: only the
    specific pytest layout is exempted. Any path under /tmp that does NOT
    contain "pytest-of-" is still checked.
    """
    try:
        tmp_dir = Path(tempfile.gettempdir()).resolve()
        resolved = repo_root.resolve()
        if not str(resolved).startswith(str(tmp_dir)):
            return False
        return "pytest-of-" in str(resolved)
    except OSError:
        return False


class _CommitIdentity(NamedTuple):
    sha: str
    author_name: str
    author_email: str
    committer_name: str
    committer_email: str


def _list_commits(push_range: str, repo_root: Path) -> list[_CommitIdentity]:
    """Return commit identities for the push range via git log."""
    result = subprocess.run(
        [
            "git", "log",
            "--format=%H|%an|%ae|%cn|%ce",
            push_range,
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            f"ERROR: git log failed for range '{push_range}': {result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(2)

    commits = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 4)
        if len(parts) != 5:
            continue
        commits.append(
            _CommitIdentity(
                sha=parts[0],
                author_name=parts[1],
                author_email=parts[2],
                committer_name=parts[3],
                committer_email=parts[4],
            )
        )
    return commits


class CheckResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


def run_check(push_range: str, repo_root: Path) -> CheckResult:
    """Run the placeholder check and return a CheckResult.

    Separated from main() so tests can call it directly without spawning
    a subprocess.
    """
    # Inline the guard logic so we can return structured results for testing.
    from scripts.github_core.placeholder_identity import is_placeholder_identity

    if _is_pytest_tmp(repo_root):
        msg = f"SKIP: placeholder identity check (repo is under pytest tmp_path: {repo_root})\n"
        return CheckResult(returncode=0, stdout=msg, stderr="")

    commits = _list_commits(push_range, repo_root)
    violations: list[str] = []

    for commit in commits:
        short = commit.sha[:12]
        if is_placeholder_identity(commit.author_name, commit.author_email):
            violations.append(
                f"ERROR: commit {short}: placeholder identity in author: "
                f"{commit.author_name} <{commit.author_email}>"
            )
        if is_placeholder_identity(commit.committer_name, commit.committer_email):
            violations.append(
                f"ERROR: commit {short}: placeholder identity in committer: "
                f"{commit.committer_name} <{commit.committer_email}>"
            )

    if violations:
        err = "\n".join(violations) + "\n"
        err += (
            "\nPlaceholder identity 'Test <test@test.com>' detected in push range.\n"
            "This identity leaks from pytest fixtures writing git config with wrong cwd.\n"
            "Fix: ensure test fixtures do not modify git config outside their tmp_path.\n"
            "See: issue #2466, scripts/github_core/placeholder_identity.py\n"
        )
        return CheckResult(returncode=1, stdout="", stderr=err)

    return CheckResult(returncode=0, stdout="", stderr="")


def main(argv: list[str] | None = None) -> int:
    """Entry point for CLI use from .githooks/pre-push."""
    parser = argparse.ArgumentParser(
        description="Check push range for placeholder git identities.",
    )
    parser.add_argument(
        "--push-range",
        required=True,
        help="Git range to check, e.g. <base>..<head>",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: cwd)",
    )
    args = parser.parse_args(argv)

    result = run_check(push_range=args.push_range, repo_root=args.repo_root)

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
