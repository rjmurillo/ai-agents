#!/usr/bin/env python3
"""Changed-path-since-base discovery, shared by the pre-PR target-scoping
gates (markdown lint, workflow YAML, YAML style).

Extracted from ``checks_tooling.py`` (round 2 review, perf/git-hook-latency)
to keep that module under the file-size ceiling once the union grew from
three git sources to four and gained a hard-failure path for a changed path
that vanishes from the worktree (item 1 and item 2 of that review). Imported
back into ``checks_tooling`` so existing callers and tests keep working.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import _resolve_branch_base_ref, _run_subprocess  # noqa: E402


def _git_paths_z(
    repo_root: Path, args: list[str], warn_label: str, action: str
) -> list[str] | None:
    """Run a git subcommand that lists paths NUL-delimited; None on failure.

    ``args`` is the argv after ``git -C <repo_root>`` (each subcommand's own
    ``-z``/``--name-only`` flags). ``-z`` keeps Unicode/space paths intact:
    verified this session, plain ``git diff --name-only`` C-quotes
    ``日本語.md`` as an octal escape; ``-z`` prints raw UTF-8, NUL-terminated.
    """
    exit_code, stdout, stderr = _run_subprocess(
        ["git", "-C", str(repo_root), *args],
        timeout=30,
    )
    if exit_code != 0:
        print(f"[WARNING] {warn_label} target narrowing skipped: {action} failed: {stderr}")
        return None
    return [path for path in stdout.split("\0") if path]


def _changed_paths_since_base(repo_root: Path, warn_label: str) -> list[str] | None:
    """Return the union of changed paths, or None for full-scan fallback.

    Shared by the markdown/workflow/yaml target helpers. Unions four
    signals, collected SEPARATELY (all NUL-delimited, see
    :func:`_git_paths_z`), so a worktree-only edit is never invisible:

    1. Committed changes since the base ref (``<base>...HEAD``).
    2. Staged changes against HEAD (``git diff --cached HEAD``): the index.
    3. Unstaged changes (``git diff``, no revision arg): the worktree
       against the index.
    4. Untracked files (``git ls-files --others --exclude-standard``).

    Signals 2 and 3 replace a single two-dot ``git diff HEAD`` call from an
    earlier version. ``git diff HEAD`` (no ``--cached``) compares the
    WORKTREE directly to HEAD, bypassing the index -- so staging a change
    and then reverting the worktree copy back to HEAD content (without
    touching the index, e.g. ``git show HEAD:path > path``) made that
    two-dot diff report NO difference, hiding a change that would still
    land in the next commit. Verified this session (git 2.43): that exact
    sequence left ``git diff HEAD`` empty while ``git diff --cached HEAD``
    and ``git diff`` (no args) both correctly reported the path.

    Returns None (full-scan fallback) when the base ref cannot be resolved
    or ANY command fails -- a failure is a proof failure, not "no changes".
    Returns ``[]`` for a clean worktree. ACMR filtering (Added, Copied,
    Modified, Renamed; no Deleted) applies to all three diffs; untracked
    files are included as-is. :func:`_filtered_targets` verifies each
    matching path is still on disk and fails loudly if it is not, rather
    than silently dropping it or falling back to a full scan.
    """
    base_ref = _resolve_branch_base_ref(repo_root)
    if base_ref is None:
        print(f"[WARNING] {warn_label} target narrowing skipped: no base ref resolved")
        return None

    diff_filter = ["diff", "--name-only", "-z", "--diff-filter=ACMR"]
    sources = (
        (diff_filter + [f"{base_ref}...HEAD"], "git diff (base ref)"),
        (diff_filter + ["--cached", "HEAD"], "git diff (staged)"),
        (diff_filter, "git diff (unstaged)"),
        (["ls-files", "--others", "--exclude-standard", "-z"], "git ls-files (untracked)"),
    )

    seen: set[str] = set()
    changed_paths: list[str] = []
    for args, action in sources:
        group = _git_paths_z(repo_root, args, warn_label, action)
        if group is None:
            return None
        for path in group:
            if path not in seen:
                seen.add(path)
                changed_paths.append(path)
    return changed_paths


class ChangedPathMissingError(RuntimeError):
    """A path git reports as changed in a committed or staged source is
    absent from the worktree, so the validator cannot inspect the exact
    content that would be pushed.

    ``--diff-filter=ACMR`` (applied to every diff source in
    :func:`_changed_paths_since_base`) already excludes Deleted, so a
    reported-but-missing path always traces back to the COMMITTED or
    STAGED sources disagreeing with the current worktree -- not just one
    scenario:

    * The committed-range source (``base...HEAD``) reports a path because
      it is genuinely part of HEAD's history (the commit that will be
      pushed). A LATER, uncommitted change -- staged (``git rm``) or
      unstaged (a bare ``rm``) -- can remove it from disk without
      touching what HEAD actually contains. The file is still part of
      what gets pushed; the validator cannot see its pushed content right
      now, which is exactly the gap this class exists to close. Staging
      the deletion does NOT fix this: it changes the index, not HEAD, and
      HEAD is what a push actually sends.
    * The staged source (``git diff --cached HEAD``) reports a path as
      Added/Modified against the index, but the worktree copy was then
      deleted out of band (a dirty deletion) without staging that
      removal.

    Silently dropping the path would validate a subset of what will
    actually be pushed; falling back to a full-repo scan cannot see the
    committed/staged content either. Both are worse than failing loudly.
    """


def _missing_path_message(repo_root: Path, warn_label: str, missing: list[str]) -> str:
    """Build the fail-closed message for paths reported changed but absent.

    Cheaply distinguishes a staged deletion (index no longer has the path
    at all -- ``git rm``, or ``git add`` of a removal) from every other
    cause (dirty deletion, branch switch, stash, etc.) with one extra
    NUL-delimited git call, reusing :func:`_git_paths_z` rather than adding
    a new abstraction. The distinction is diagnostic only: a failed lookup
    here (network/perf issue, not correctness-critical) degrades to "reason
    unknown" for every path rather than changing whether the gate fails.
    The remediation guidance is identical either way, because staging the
    deletion alone never resolves the committed-range case (see
    :class:`ChangedPathMissingError`).
    """
    staged_deletions = _git_paths_z(
        repo_root,
        ["diff", "--name-only", "-z", "--diff-filter=D", "--cached", "HEAD"],
        warn_label,
        "git diff (staged deletions, diagnostic)",
    )
    staged_deletion_set = set(staged_deletions or [])
    lines = [
        f"{warn_label}: git reports the following path(s) changed in a "
        "committed or staged source, but they are absent from the "
        "worktree, so this gate cannot inspect the exact pushed/intended "
        "content:",
    ]
    for path in missing:
        reason = "staged deletion" if path in staged_deletion_set else "reason unknown"
        lines.append(f"  - {path} ({reason})")
    lines.append(
        "Commit the deletion, restore the file, or clean/stash the "
        "worktree before pushing; do not ignore this gate."
    )
    return "\n".join(lines)


def _filtered_targets(
    repo_root: Path, warn_label: str, predicate: Callable[[str], bool]
) -> list[str] | None:
    """Return changed paths matching ``predicate``, verified present on disk.

    None/[] pass through unchanged from :func:`_changed_paths_since_base`.
    Raises :class:`ChangedPathMissingError` if any predicate-matching path
    is not on disk (see that class's docstring for why this is a hard
    failure, not a silent filter or a full-scan fallback).
    """
    changed = _changed_paths_since_base(repo_root, warn_label)
    if changed is None:
        return None
    matches = [path for path in changed if predicate(path)]
    missing = [path for path in matches if not (repo_root / path).is_file()]
    if missing:
        raise ChangedPathMissingError(_missing_path_message(repo_root, warn_label, missing))
    return matches
