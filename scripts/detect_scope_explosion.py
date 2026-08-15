#!/usr/bin/env python3
# taste-lint: ignore file-size  # Cohesive pipeline; splitting adds coupling
"""Detect scope explosion by counting files changed since branch diverged from main.

Tracks cumulative PR size and provides early warnings before PRs grow too large.

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
from pathlib import Path

# Add project root to path for imports
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.scope_pr_base import (  # noqa: E402
    is_credible_rescope,
    resolve_pr_base_branch,
    strip_remote_prefix,
)
from scripts.validation.git_hook_policy import (  # noqa: E402
    _is_generated,
)

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
    generated_count: int = 0


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


def is_ancestor(commit: str, ref: str) -> bool:
    """Return True when ``commit`` is an ancestor-or-equal of ``ref``."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, ref],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _partition_generated(files: list[str], repo_root: Path | None = None) -> tuple[list[str], int]:
    """Separate authored files from generated files.

    Returns:
        Tuple of (authored_files, generated_count).
    """
    authored = []
    generated = 0
    for f in files:
        if _is_generated(f, repo_root=repo_root):
            generated += 1
        else:
            authored.append(f)
    return authored, generated


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
    if merge_head:
        # During an in-progress merge, measure the final staged tree against
        # the resolved PR base ref. This matches the eventual PR diff against
        # that base, so branch-local staged work, local-main-only commits, and
        # sibling-branch merges all count, while base-branch files already
        # present on the resolved base stay out of scope. Do not require a
        # merge-base here: unrelated-history merges still produce a valid
        # staged diff against the base ref, and blocking on merge-base would
        # turn a countable merge into a hard error.
        files = sorted(set(get_index_files_against_ref(base_ref)))
        authored, gen_count = _partition_generated(files)
        return ScopeResult(
            file_count=len(authored),
            merge_base=base_ref[:12],
            current_branch=branch,
            files=tuple(authored),
            generated_count=gen_count,
        )

    merge_base = get_merge_base(base_branch, base_ref)
    if not merge_base:
        raise ScopeDetectionError(f"could not determine merge base with {base_branch}")

    # Count the final staged tree against the merge base, matching the
    # in-progress-merge path above. `git diff --cached --diff-filter=ACMR
    # <base>` reflects the index as it will be committed, so a staged deletion
    # of a branch-only file drops out of the count: the file is absent from the
    # index and from the base, so it produces no diff entry. The former
    # approach unioned the committed diff (merge_base..HEAD) with the staged
    # ACMR set, which could not subtract such a deletion because the committed
    # diff still listed it (Issue #3171).
    files = sorted(set(get_index_files_against_ref(merge_base)))
    authored, gen_count = _partition_generated(files)

    return ScopeResult(
        file_count=len(authored),
        merge_base=merge_base[:12],
        current_branch=branch,
        files=tuple(authored),
        generated_count=gen_count,
    )


def rescope_against_pr_base(requested_base: str | None, blocked: ScopeResult) -> ScopeResult | None:
    """Re-measure a blocking result against the PR's real base branch.

    A stacked PR sits on another PR, not on main. Measured against main it
    carries every file its whole stack touched, which is not the surface any
    reviewer of this PR reads. Observed on PR #4728: 52 files against main,
    13 against its actual base.

    Called only when the main-relative count already blocks, so the gh lookup
    costs nothing on the path almost every commit takes.

    This function can only ever *remove* a block, so every uncertain case has
    to resolve to None and keep the original result. Four conditions do:

    1. A merge is in progress. ``detect_scope`` picks between the MERGE_HEAD
       path and the merge-base path by testing ``is_ancestor(MERGE_HEAD,
       base_ref)``, and that test depends on which base is passed. A second
       call with a different base can therefore compare in a different mode
       than the first, and the two numbers are not comparable. Skip entirely.
    2. gh cannot name exactly one open PR base.
    3. The PR base is the branch already measured.
    4. The re-measurement is not a credible narrowing of the first one. See
       ``is_credible_rescope``.

    The branch name comes from ``blocked.current_branch`` rather than a fresh
    ``get_current_branch()`` call. Re-reading would let a branch switch between
    the two measurements produce a PR base belonging to a different branch than
    the one that was measured.
    """
    if get_merge_head_commit() is not None:
        return None
    branch = blocked.current_branch
    if not branch:
        return None
    pr_base = resolve_pr_base_branch(branch)
    if pr_base is None:
        return None
    if pr_base == strip_remote_prefix(requested_base or "main"):
        return None
    try:
        rescoped = detect_scope(pr_base)
    except ScopeDetectionError:
        return None
    if not is_credible_rescope(rescoped, blocked, is_ancestor):
        return None
    assert rescoped is not None  # narrowed by is_credible_rescope
    print(
        f"Measured against origin/{pr_base}, this PR's actual base: "
        f"{rescoped.file_count} files (against "
        f"{requested_base or 'main'}: {blocked.file_count}).",
        file=sys.stderr,
    )
    return rescoped


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
    gen_note = f" ({result.generated_count} generated excluded)" if result.generated_count else ""

    if count < WARN_THRESHOLD:
        if not quiet:
            print(f"PR size: {format_bar(count, WARN_THRESHOLD)}{gen_note}")
        return 0

    if count < STRONG_WARN_THRESHOLD:
        print(f"WARNING: PR scope growing. {format_bar(count, WARN_THRESHOLD)}{gen_note}")
        print(f"  Branch: {result.current_branch}")
        print("  Consider reviewing scope before the PR grows further.")
        return 0

    if count <= BLOCK_THRESHOLD:
        print(f"WARNING: PR scope is large. {format_bar(count, STRONG_WARN_THRESHOLD)}{gen_note}")
        print(f"  Branch: {result.current_branch}")
        print(f"  {count} files changed since diverging from main.{gen_note}")
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
    print(f"BLOCKED: PR scope explosion detected. {format_bar(count, BLOCK_THRESHOLD)}{gen_note}")
    print(f"  Branch: {result.current_branch}")
    print(f"  {count} files changed (over the {BLOCK_THRESHOLD}-file hard limit).{gen_note}")
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

        # Consult the PR base only when the cheap measurement is about to
        # block. On the path almost every commit takes this adds no work and
        # no network call.
        if result.file_count > BLOCK_THRESHOLD:
            rescoped = rescope_against_pr_base(args.base_branch, result)
            if rescoped is not None:
                result = rescoped

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
