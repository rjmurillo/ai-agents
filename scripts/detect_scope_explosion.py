#!/usr/bin/env python3
"""Detect scope explosion by counting files changed since branch diverged from main.

Tracks cumulative PR size and provides early warnings before PRs grow too large.
Designed to run as a named pre-commit validator from lefthook.yml.

Thresholds:
  10 files: Warning (suggest reviewing scope)
  20 files: Strong warning (suggest splitting)
  50 files: Hard limit, still allowed (strong warning)
  Over 50:  Block commit

Bypass: Set SKIP_SCOPE_CHECK=1 environment variable for justified large PRs.

EXIT CODES:
  0  - Success: File count within limits (or warnings issued)
  1  - Block: File count exceeds hard limit (over 50 files)
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


class ScopeDetectionError(RuntimeError):
    """Raised when the scope gate cannot determine the branch delta."""


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
        encoding="utf-8",
        errors="replace",
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
        encoding="utf-8",
        errors="replace",
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
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


def get_merge_head_commit() -> str | None:
    """Return MERGE_HEAD commit SHA while a merge is in progress."""
    return get_ref_commit("MERGE_HEAD")


def is_ancestor_or_equal(ancestor_ref: str, descendant_ref: str) -> bool:
    """Return True when ancestor_ref is an ancestor of descendant_ref."""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor_ref, descendant_ref],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise ScopeDetectionError(
        "git merge-base --is-ancestor "
        f"{ancestor_ref} {descendant_ref} failed (rc={result.returncode}): "
        f"{result.stderr.strip()}"
    )


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


def get_merge_base(base_branch: str, base_ref: str | None = None) -> str | None:
    """Find the merge base between HEAD and the base branch.

    Prefers ``origin/<base_branch>`` over the local branch ref to avoid stale
    merge bases in worktrees where local ``main`` lags the remote
    (Issue #2207).

    Args:
        base_branch: The branch to compare against (e.g. "main").
        base_ref: The already-resolved ref to compare against.

    Returns:
        Merge base commit SHA, or None if not found.
    """
    if base_ref is None:
        base_ref = resolve_base_ref(base_branch)
    if base_ref is None:
        return None
    result = subprocess.run(
        ["git", "merge-base", "HEAD", base_ref],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


def get_index_files_against_ref(base_ref: str) -> list[str]:
    """Get staged result files that differ from a base ref.

    Raises:
        ScopeDetectionError: If the git diff command fails.
    """
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", base_ref],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise ScopeDetectionError(
            f"git diff --cached against {base_ref} failed (rc={result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def get_head_files_against_ref(base_ref: str) -> list[str]:
    """Get committed HEAD files that differ from a base ref.

    Raises:
        ScopeDetectionError: If the git diff command fails.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base_ref}...HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise ScopeDetectionError(
            f"git diff against {base_ref}...HEAD failed (rc={result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def detect_scope(base_branch: str = "main") -> ScopeResult | None:
    """Detect scope explosion on the current branch.

    Args:
        base_branch: The branch to compare against.

    Returns:
        ScopeResult with file counts, or None if detection not applicable.
    """
    branch = get_current_branch()
    if branch is None:
        raise ScopeDetectionError("detached HEAD: scope check cannot determine the current branch")
    if branch in TRUNK_BRANCHES:
        return None

    base_ref = resolve_base_ref(base_branch)
    if base_ref is None:
        raise ScopeDetectionError(f"could not resolve base branch {base_branch}")

    merge_head = get_merge_head_commit()
    merge_base = get_merge_base(base_branch, base_ref)
    if not merge_base:
        raise ScopeDetectionError(f"could not determine merge base with {base_branch}")

    if merge_head:
        base_lineage_refs: list[str] = []
        for candidate_ref in (base_ref, base_branch):
            if candidate_ref not in base_lineage_refs and _ref_exists(candidate_ref):
                base_lineage_refs.append(candidate_ref)

        if any(
            is_ancestor_or_equal(merge_head, candidate_ref) for candidate_ref in base_lineage_refs
        ):
            # When MERGE_HEAD is the base branch being merged, diff the final
            # staged tree against that exact base-side commit. This keeps the
            # upstream merge files out of scope while still counting any new
            # branch-local files staged after `git merge --no-commit`, even
            # when local `main` has advanced past `origin/main`.
            files = sorted(set(get_index_files_against_ref(merge_head)))
        else:
            # A sibling merge can leave MERGE_HEAD off the base lineage.
            # Counting the staged index against that sibling inflates scope by
            # upstream files, so fall back to committed branch-authored files
            # against the true merge base.
            files = sorted(set(get_head_files_against_ref(merge_base)))
        return ScopeResult(
            file_count=len(files),
            merge_base=merge_base[:12],
            current_branch=branch,
            files=tuple(files),
        )

    # Count the final staged tree against the merge base, matching the
    # in-progress-merge path above. `git diff --cached --diff-filter=ACMR
    # <base>` reflects the index as it will be committed, so a staged deletion
    # of a branch-only file drops out of the count: the file is absent from the
    # index and from the base, so it produces no diff entry. The former
    # approach unioned the committed diff (merge_base..HEAD) with the staged
    # ACMR set, which could not subtract such a deletion because the committed
    # diff still listed it (Issue #3171).
    files = sorted(set(get_index_files_against_ref(merge_base)))

    return ScopeResult(
        file_count=len(files),
        merge_base=merge_base[:12],
        current_branch=branch,
        files=tuple(files),
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


def report(result: ScopeResult, quiet: bool = False, from_prepush: bool = False) -> int:
    """Report scope status and return exit code.

    Args:
        result: Detection result.
        quiet: Suppress non-error output.
        from_prepush: True when invoked from the pre-push hook (files already
            committed; bypass requires ``git push``, not ``git commit``).

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

    if count <= BLOCK_THRESHOLD:
        print(f"WARNING: PR scope is large. {format_bar(count, STRONG_WARN_THRESHOLD)}")
        print(f"  Branch: {result.current_branch}")
        print(f"  {count} files changed since diverging from main.")
        print("  Strongly consider splitting this into smaller PRs.")
        if not from_prepush:
            print("  Remediation:")
            print("    1. Commit current work")
            print("    2. Create a PR for the current scope")
            print("    3. Start a new branch for remaining work")
        else:
            print("  Remediation: split commits onto separate branches and push each.")
        return 0

    # Block: count exceeds the hard limit (50 is allowed; 51+ blocks).
    print(f"BLOCKED: PR scope explosion detected. {format_bar(count, BLOCK_THRESHOLD)}")
    print(f"  Branch: {result.current_branch}")
    print(f"  {count} files changed (over the {BLOCK_THRESHOLD}-file hard limit).")
    print("  This PR is too large to review effectively.")
    print("")
    if not from_prepush:
        print("  Remediation:")
        print("    1. Split into smaller, focused PRs")
        print("    2. Use 'git stash' to save uncommitted work")
        print("    3. Create a PR for the current scope, then continue")
    else:
        print("  Remediation: split commits onto separate branches and push each.")
    print("")
    print("  Bypass (justified large PRs only):")
    bypass_cmd = "git push" if from_prepush else "git commit"
    print(f"    SKIP_SCOPE_CHECK=1 {bypass_cmd} ...")
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
        default=None,
        help="Base branch to compare against (default: main). When supplied, the"
        " script treats itself as running from the pre-push hook and adjusts"
        " bypass instructions accordingly.",
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

        result = detect_scope(args.base_branch or "main")
        if result is None:
            # Trunk branch only. Unknown scope raises ScopeDetectionError.
            return 0

        from_prepush = args.base_branch is not None
        return report(result, args.quiet, from_prepush=from_prepush)

    except ScopeDetectionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
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
