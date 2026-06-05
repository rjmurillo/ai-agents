#!/usr/bin/env python3
"""Detect scope explosion by counting files changed since branch diverged from main.

Tracks cumulative PR size and provides early warnings before PRs grow too large.
Designed to run as a pre-commit check, delegated from .githooks/pre-commit.

Thresholds:
  10 files: Warning (suggest reviewing scope)
  20 files: Strong warning (suggest splitting)
  50 files: Block commit (hard limit)

Bypass: Set SKIP_SCOPE_CHECK=1 environment variable for justified large PRs.

EXIT CODES:
  0  - Success: File count within limits (or warnings issued)
  1  - Block: File count exceeds hard limit (50 files)
  2  - Error: Could not determine branch state

See: ADR-035 Exit Code Standardization
Related: Issue #944, PR #908 (95 files)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass

# Thresholds for scope explosion detection
WARN_THRESHOLD = 10
STRONG_WARN_THRESHOLD = 20
BLOCK_THRESHOLD = 50

# Branches that are not feature branches (no scope tracking needed)
TRUNK_BRANCHES = frozenset({"main", "master"})


@dataclass(frozen=True)
class ScopeResult:
    """Result of scope explosion detection."""

    file_count: int
    merge_base: str
    current_branch: str
    files: tuple[str, ...]


def get_current_branch() -> str | None:
    """Get the current git branch name.

    Returns:
        Branch name, or None if detached HEAD.
    """
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    branch = result.stdout.strip()
    return branch if branch else None


def _ref_exists(ref: str) -> bool:
    """Return True if a git ref resolves locally.

    Args:
        ref: The ref name to check (e.g. "origin/main", "main").
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def get_ref_commit(ref: str) -> str | None:
    """Return the commit SHA for a resolved ref, or None on failure."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


def get_merge_head_commit() -> str | None:
    """Return MERGE_HEAD commit SHA while a merge is in progress."""
    return get_ref_commit("MERGE_HEAD")


def resolve_base_ref(base_branch: str) -> str | None:
    """Resolve the most accurate base ref for diff comparison.

    In a worktree (or any checkout where the local trunk branch lags the
    remote), the local ``main`` ref can be stale and produce a diff full of
    files the PR never touched. Prefer ``origin/<base>`` when it exists so the
    scope check reflects the real PR diff (Issue #2207).

    Resolution order:
      1. ``origin/<base_branch>`` if the ref exists locally.
      2. ``<base_branch>`` as a local fallback.
      3. None if neither resolves.

    Args:
        base_branch: The plain branch name (e.g. "main").

    Returns:
        The resolved ref string, or None if no candidate exists.
    """
    remote_ref = f"origin/{base_branch}"
    if _ref_exists(remote_ref):
        return remote_ref
    if _ref_exists(base_branch):
        return base_branch
    return None


def get_merge_base(base_branch: str) -> str | None:
    """Find the merge base between HEAD and the base branch.

    Prefers ``origin/<base_branch>`` over the local branch ref to avoid stale
    merge bases in worktrees where local ``main`` lags the remote
    (Issue #2207).

    Args:
        base_branch: The branch to compare against (e.g. "main").

    Returns:
        Merge base commit SHA, or None if not found.
    """
    base_ref = resolve_base_ref(base_branch)
    if base_ref is None:
        return None
    result = subprocess.run(
        ["git", "merge-base", "HEAD", base_ref],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


def get_changed_files(merge_base: str) -> list[str]:
    """Get files changed between merge base and HEAD.

    Args:
        merge_base: The commit to compare from.

    Returns:
        List of changed file paths.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", merge_base, "HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def get_staged_new_files(merge_base: str) -> list[str]:
    """Get staged files not yet committed that are new since merge base.

    Includes currently staged changes to give accurate pre-commit count.

    Args:
        merge_base: The commit to compare from.

    Returns:
        List of staged file paths not already in the committed diff.
    """
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def get_index_files_against_ref(base_ref: str) -> list[str]:
    """Get staged result files that differ from a base ref."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", base_ref],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def detect_scope(base_branch: str = "main") -> ScopeResult | None:
    """Detect scope explosion on the current branch.

    Args:
        base_branch: The branch to compare against.

    Returns:
        ScopeResult with file counts, or None if detection not applicable.
    """
    branch = get_current_branch()
    if not branch or branch in TRUNK_BRANCHES:
        return None

    base_ref = resolve_base_ref(base_branch)
    if base_ref is None:
        return None

    merge_head = get_merge_head_commit()
    if merge_head:
        # During an in-progress merge, the staged index already contains every
        # file from the upstream branch being merged. Counting that against the
        # base ref would surface upstream files as if they were PR changes
        # (Issue #2376 — observed 86 files reported when the real PR diff was
        # 13). Compare the staged result directly against MERGE_HEAD so we
        # only count files this PR actually touches relative to what is being
        # merged in.
        files = sorted(set(get_index_files_against_ref(merge_head)))
        base_commit = get_ref_commit(base_ref) or merge_head
        return ScopeResult(
            file_count=len(files),
            merge_base=base_commit[:12],
            current_branch=branch,
            files=tuple(files),
        )

    merge_base = get_merge_base(base_branch)
    if not merge_base:
        return None

    committed_files = get_changed_files(merge_base)
    staged_files = get_staged_new_files(merge_base)

    # Union of committed and staged files for total count
    all_files = sorted(set(committed_files) | set(staged_files))

    return ScopeResult(
        file_count=len(all_files),
        merge_base=merge_base[:12],
        current_branch=branch,
        files=tuple(all_files),
    )


def format_bar(count: int, threshold: int) -> str:
    """Format a simple progress bar showing file count vs threshold.

    Args:
        count: Current file count.
        threshold: Warning threshold for context.

    Returns:
        Formatted bar string.
    """
    max_bar = 30
    filled = min(count, BLOCK_THRESHOLD)
    bar_len = int((filled / BLOCK_THRESHOLD) * max_bar)
    bar = "#" * bar_len + "-" * (max_bar - bar_len)
    return f"[{bar}] {count}/{BLOCK_THRESHOLD} files"


def report(result: ScopeResult, quiet: bool = False) -> int:
    """Report scope status and return exit code.

    Args:
        result: Detection result.
        quiet: Suppress non-error output.

    Returns:
        Exit code: 0 for pass/warn, 1 for block.
    """
    count = result.file_count

    if count < WARN_THRESHOLD:
        if not quiet:
            print(f"PR size: {format_bar(count, WARN_THRESHOLD)}")
        return 0

    if count < STRONG_WARN_THRESHOLD:
        print(f"WARNING: PR scope growing. {format_bar(count, WARN_THRESHOLD)}")
        print(f"  Branch: {result.current_branch}")
        print("  Consider reviewing scope before the PR grows further.")
        return 0

    if count < BLOCK_THRESHOLD:
        print(f"WARNING: PR scope is large. {format_bar(count, STRONG_WARN_THRESHOLD)}")
        print(f"  Branch: {result.current_branch}")
        print(f"  {count} files changed since diverging from main.")
        print("  Strongly consider splitting this into smaller PRs.")
        print("  Remediation:")
        print("    1. Commit current work")
        print("    2. Create a PR for the current scope")
        print("    3. Start a new branch for remaining work")
        return 0

    # Block threshold exceeded
    print(f"BLOCKED: PR scope explosion detected. {format_bar(count, BLOCK_THRESHOLD)}")
    print(f"  Branch: {result.current_branch}")
    print(f"  {count} files changed (hard limit: {BLOCK_THRESHOLD}).")
    print("  This PR is too large to review effectively.")
    print("")
    print("  Remediation:")
    print("    1. Split into smaller, focused PRs")
    print("    2. Use 'git stash' to save uncommitted work")
    print("    3. Create a PR for the current scope, then continue")
    print("")
    print("  Bypass (justified large PRs only):")
    print("    SKIP_SCOPE_CHECK=1 git commit ...")
    return 1


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-branch",
        default="main",
        help="Base branch to compare against (default: main)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-error output",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point. Returns exit code.

    Returns:
        0 on success/warning, 1 on block, 2 on error.
    """
    try:
        args = parse_args()

        # Check bypass
        if os.environ.get("SKIP_SCOPE_CHECK") == "1":
            print("Scope check bypassed (SKIP_SCOPE_CHECK=1)")
            return 0

        result = detect_scope(args.base_branch)
        if result is None:
            # Not on a feature branch or no merge base found
            return 0

        return report(result, args.quiet)

    except subprocess.TimeoutExpired:
        print("ERROR: Git command timed out during scope detection", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 1
    except Exception as e:
        print(f"ERROR: Scope detection failed: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
