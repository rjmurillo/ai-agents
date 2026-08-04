"""Detect remote branches whose PR merged but whose tip is not an ancestor of main.

A squash merge leaves the original branch tip as an orphan: HEAD of the branch
is not an ancestor of main even though the PR shows as merged. Any commit pushed
to the branch after the squash merge is silently dropped when the branch is
deleted. This script surfaces those cases so a human can decide whether to
recover the diff.

Exit codes:
  0 - no unlanded commits found
  1 - one or more branches have unlanded commits
  2 - configuration error
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import NamedTuple

_GIT_TIMEOUT = 30


def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=cwd,
        timeout=_GIT_TIMEOUT,
    )


class UnlandedBranch(NamedTuple):
    branch: str
    tip_sha: str
    commit_count: int


def _remote_merged_branches(repo: str, base_ref: str) -> list[str]:
    """Return remote branches that are NOT ancestors of base_ref."""
    result = _git(
        ["branch", "-r", "--no-merged", base_ref, "--format=%(refname:short)"],
        repo,
    )
    if result.returncode != 0:
        return []
    return [b.strip() for b in result.stdout.splitlines() if b.strip()]


def _is_ancestor(sha: str, base_ref: str, repo: str) -> bool:
    result = _git(["merge-base", "--is-ancestor", sha, base_ref], repo)
    return result.returncode == 0


def _tip_sha(branch: str, repo: str) -> str:
    result = _git(["rev-parse", branch], repo)
    return result.stdout.strip() if result.returncode == 0 else ""


def _commit_count_not_in_base(branch: str, base_ref: str, repo: str) -> int:
    result = _git(["rev-list", "--count", f"{base_ref}..{branch}"], repo)
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def _branch_pr_merged(branch: str) -> bool:
    """Return True if GitHub reports the PR for this branch as merged.

    Uses gh CLI (REST). Returns False on any error so callers treat unknowns as
    not-merged and skip them, keeping output conservative.
    """
    clean = branch.removeprefix("origin/")
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                "/repos/{owner}/{repo}/pulls",
                "-X",
                "GET",
                "-f",
                f"head={clean}",
                "-f",
                "state=closed",
                "--jq",
                ".[].merged_at",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=15,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def scan(repo: str, base_ref: str, *, check_github: bool) -> list[UnlandedBranch]:
    """Return branches with commits not yet in base_ref."""
    not_merged = _remote_merged_branches(repo, base_ref)
    results: list[UnlandedBranch] = []
    for branch in not_merged:
        tip = _tip_sha(branch, repo)
        if not tip:
            continue
        count = _commit_count_not_in_base(branch, base_ref, repo)
        if count == 0:
            continue
        if check_github and not _branch_pr_merged(branch):
            continue
        results.append(UnlandedBranch(branch=branch, tip_sha=tip, commit_count=count))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="path to git repo (default: .)")
    parser.add_argument(
        "--base-ref", default="origin/main", help="base ref to check against"
    )
    parser.add_argument(
        "--check-github",
        action="store_true",
        help="filter to branches whose PR is confirmed merged on GitHub (requires gh CLI)",
    )
    args = parser.parse_args(argv)

    try:
        unlanded = scan(args.repo, args.base_ref, check_github=args.check_github)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not unlanded:
        print("No unlanded commits found.")
        return 0

    print(f"WARNING: {len(unlanded)} branch(es) have commits not in {args.base_ref}:")
    for b in unlanded:
        print(f"  {b.branch}  tip={b.tip_sha[:12]}  commits={b.commit_count}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
