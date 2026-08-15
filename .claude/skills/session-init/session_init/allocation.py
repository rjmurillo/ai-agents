"""Session-number allocation scans across local tree and remote-tracking refs.

One authoritative home for the scans both session-log creators use to pick
the next session number (issues #2379, #4561, #4751):

- ``max_session_in_names``: highest number among candidate file names.
- ``origin_main_max_session``: numbers already merged to origin/main.
- ``sibling_refs_max_session``: numbers committed on ANY remote-tracking ref
  under ``refs/remotes/origin/``, so unmerged sibling branches are visible at
  allocation time (issue #4751).
- ``remote_max_session``: the allocation policy combining the two.

Failure semantics (issue #4751): ``sibling_refs_max_session`` returns ``None``
on any probe failure and an ``int`` (possibly 0) only for a complete reading.
A reading that cannot separate "no sessions exist on siblings" from "the scan
could not run" is not evidence of absence, so an incomplete scan never
reports 0.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Iterable

SESSION_NUM_RE = re.compile(r"session-(\d+)")

# Per-git-invocation timeout. Remote-tracking refs are local, so every call
# here is offline; the timeout guards against a hung git, not the network.
GIT_TIMEOUT_SECONDS = 10

# Whole-scan budget for the sibling-ref walk. One ls-tree per unique commit
# costs milliseconds; the budget bounds pathological clones with thousands of
# refs. Exceeding it aborts the scan as a probe failure (None), never as a
# partial reading passed off as complete.
SIBLING_SCAN_BUDGET_SECONDS = 60.0

_SESSIONS_PATH = ".agents/sessions/"


def max_session_in_names(names: Iterable[str]) -> int:
    """Highest session number among ``*.json`` file names, or 0 when none."""
    max_num = 0
    for name in names:
        m = SESSION_NUM_RE.search(name)
        if m and name.endswith(".json"):
            max_num = max(max_num, int(m.group(1)))
    return max_num


def _run_git(args: list[str], repo_root: str | None) -> subprocess.CompletedProcess[str] | None:
    """Run a git command, returning None on any spawn/timeout failure."""
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
            cwd=repo_root,
        )
    except (subprocess.SubprocessError, OSError):
        return None


def origin_main_max_session(repo_root: str | None = None) -> int:
    """Highest session number recorded under origin/main, or 0 when unknown.

    Parallel autofix branches fork from the same main and each scans only its
    own working tree, so two branches can allocate the same next number
    (issue #2379). Reading the session files already on origin/main lets every
    branch see numbers committed by siblings that have already merged.

    origin/main is a local remote-tracking ref, so `git ls-tree` does not hit
    the network. The call is best-effort: any failure (no origin, no ref,
    timeout, git missing) returns 0 so allocation falls back to the local scan.
    """
    result = _run_git(["ls-tree", "--name-only", "origin/main", _SESSIONS_PATH], repo_root)
    if result is None or result.returncode != 0:
        return 0
    names = [os.path.basename(line) for line in result.stdout.splitlines() if line.strip()]
    return max_session_in_names(names)


def sibling_refs_max_session(repo_root: str | None = None) -> int | None:
    """Highest session number on any ``refs/remotes/origin/*`` ref.

    Scanning origin/main alone cannot see numbers a sibling branch has pushed
    but not merged, and under fleet execution siblings sit unmerged for hours,
    so that window is the normal case, not an edge (issue #4751). Walking
    every remote-tracking ref closes the pushed-but-unmerged window. It stays
    offline the same way ``git ls-tree origin/main`` does: remote-tracking
    refs are local, so nothing here touches the network, and "unreachable
    remote" surfaces as a git failure, not a hang.

    Returns an ``int`` (possibly 0) only when every ref was read: 0 means the
    scan completed and found no session files, which IS evidence of absence.
    Returns ``None`` when the reading is incomplete for any reason: ref
    enumeration failed, a per-ref ls-tree failed, git timed out, or the scan
    budget expired. Callers must treat ``None`` as a probe failure and fall
    back, never as "no sessions on siblings".
    """
    deadline = time.monotonic() + SIBLING_SCAN_BUDGET_SECONDS
    listing = _run_git(
        ["for-each-ref", "--format=%(refname) %(objectname)", "refs/remotes/origin/"],
        repo_root,
    )
    if listing is None or listing.returncode != 0:
        return None

    max_num = 0
    seen_commits: set[str] = set()
    for line in listing.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        refname, commit = parts
        if commit in seen_commits:
            # Refs at the same commit share the same sessions tree; one read
            # covers them all (origin/HEAD duplicating origin/main, etc.).
            continue
        seen_commits.add(commit)
        if time.monotonic() > deadline:
            return None
        ls = _run_git(["ls-tree", "--name-only", refname, _SESSIONS_PATH], repo_root)
        if ls is None or ls.returncode != 0:
            return None
        names = [os.path.basename(entry) for entry in ls.stdout.splitlines() if entry.strip()]
        max_num = max(max_num, max_session_in_names(names))
    return max_num


def remote_max_session(
    repo_root: str | None = None,
    *,
    sibling_scan: Callable[[str | None], int | None] | None = None,
    origin_scan: Callable[[str | None], int] | None = None,
) -> int:
    """Best-available remote session max for allocation.

    Policy: prefer the sibling-ref scan, which subsumes origin/main. On probe
    failure (None) warn and fall back to the origin/main-only scan, restoring
    the pre-#4751 behavior rather than silently allocating against nothing.

    ``sibling_scan`` / ``origin_scan`` exist so callers can route through
    their own patchable module-level names in tests; production callers omit
    them.
    """
    scan = sibling_scan if sibling_scan is not None else sibling_refs_max_session
    fallback = origin_scan if origin_scan is not None else origin_main_max_session
    sibling_max = scan(repo_root)
    if sibling_max is not None:
        return sibling_max
    print(
        "WARNING: sibling-branch session scan failed; falling back to "
        "origin/main only. Allocation may reuse a number already taken on an "
        "unmerged branch (issue #4751).",
        file=sys.stderr,
    )
    return fallback(repo_root)
