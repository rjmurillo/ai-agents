#!/usr/bin/env python3
"""Turn what the stale-entry probes found into advice a reader can act on.

A stale worktree entry can abandon three independent things, and rescuing one
rescues none of the others: a detached HEAD no ref contains, blobs staged in
its orphaned index that no commit carries, and commits its own reflog anchors
that are not ancestors of HEAD. This module builds one warning per channel and
joins them, so the report never reports the loudest loss and stays silent
about the rest.

Every function here takes ``run_git`` rather than reaching for a module-level
one. The caller already knows which worktree is safe to run git in, and for a
stale entry that is never the entry's own directory: it is gone, which is what
made it stale. Passing the runner in keeps that decision at the call site
instead of duplicating it here.

Related: Issue #2761 (worktree accumulation starves the markdown LSP).
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from scripts.maintenance import _gc_stale
else:
    try:
        from scripts.maintenance import _gc_stale
    except ModuleNotFoundError:
        import _gc_stale

from scripts.maintenance.worktree_report import (
    KEEP_STALE,
    KEEP_STALE_UNREACHABLE,
    Worktree,
)

_GIT_TIMEOUT_SECONDS = 10


def stale_keep_reason(worktree: Worktree, main_path: str, run_git: Callable[..., str]) -> str:
    """Explain a kept stale entry, and lead with everything clearing it would destroy.

    Clearing a stale entry deletes its admin directory. Three separate things
    live there that nothing else holds, and rescuing one rescues none of the
    others. The detached HEAD is abandoned when no ref contains it. The index
    anchors blobs that ``git add`` wrote but no commit carries. The reflog
    anchors commits the worktree made and then checked away from, which are not
    ancestors of HEAD and so survive no HEAD rescue. Verified against real git:
    a single entry can carry all three at once, and each needs its own command.

    Reporting only the loudest one is what makes this dangerous rather than
    merely incomplete. A reader who rescues HEAD and then clears the entry has
    followed the printed advice exactly and still lost the other two.

    Warnings come first because the message ends with a command. A reader who
    stops at the first runnable line must not have run it yet. They are joined
    with a separator that no git argument can absorb: ending a warning with
    ``.`` glues a period onto the recovery command's last token, and
    ``git branch rescue/x <sha>.`` fails with ``bad object``.

    Every git call runs in the main worktree. The stale entry's own directory
    is gone, which is what made it stale.
    """
    admin = _gc_stale.admin_dir_for(worktree.path, partial(run_git, cwd=main_path), main_path)
    if admin is None:
        head = _head_warning(worktree.head, run_git)
        lead = f"{head} | " if head else ""
        return (
            f"{lead}could not locate its admin entry, so nothing else about it "
            f"was checked; {KEEP_STALE}"
        )
    warnings = [
        _head_warning(worktree.head, run_git),
        _staged_warning(admin, worktree.head, main_path),
        _reflog_warning(admin, main_path),
    ]
    lead = "".join(f"{warning} | " for warning in warnings if warning)
    return f"{lead}{KEEP_STALE}"


def _head_warning(head: str | None, run_git: Callable[..., str]) -> str:
    """Whether clearing the entry abandons its detached HEAD."""
    if not head:
        return "its recorded HEAD is missing, so nothing about it could be rescued"
    if stale_head_is_reachable(head, run_git):
        return ""
    return f"WARNING: {KEEP_STALE_UNREACHABLE}. Rescue first: git branch rescue/{head[:12]} {head}"


def _staged_warning(admin: Path, head: str | None, main_path: str) -> str:
    """What the orphaned index holds, or why that could not be established."""
    if not head:
        return "its recorded HEAD is missing, so staged work cannot be ruled out"
    state = _gc_stale.staged_content_state(admin, head, main_path, _GIT_TIMEOUT_SECONDS)
    if state == _gc_stale.CLEAN:
        return ""
    if state == _gc_stale.UNKNOWN:
        return "its index could not be read, so staged work cannot be ruled out"
    return (
        "WARNING: its index holds staged work that no commit carries, and clearing the "
        f"entry deletes that index. Recover first: GIT_INDEX_FILE={admin / 'index'} "
        "git checkout-index -a --prefix=<somewhere>/"
    )


def _reflog_warning(admin: Path, main_path: str) -> str:
    """Which commits the admin reflog alone anchors, or why that is unknown."""
    orphans = _gc_stale.unreachable_reflog_commits(admin, main_path, _GIT_TIMEOUT_SECONDS)
    if orphans is None:
        return "its reflog could not be read, so abandoned commits cannot be ruled out"
    if not orphans:
        return ""
    rescues = " ".join(f"git branch rescue/{sha[:12]} {sha}" for sha in orphans[:3])
    more = "" if len(orphans) <= 3 else f" (and {len(orphans) - 3} more)"
    return (
        f"WARNING: its reflog is the only anchor for {len(orphans)} commit(s), and "
        f"clearing the entry deletes it. Rescue first: {rescues}{more}"
    )


def stale_head_is_reachable(head: str | None, run_git: Callable[..., str]) -> bool:
    """Is a stale worktree's HEAD still contained by some ref?

    Pruning a stale admin entry deletes the last ref that keeps a detached HEAD
    alive, so its commits become garbage-collectable. Every stale entry on this
    machine was contained when measured, but the tool must not assume that. An
    unreadable or ambiguous answer counts as unreachable, which keeps the
    fail-safe direction: refuse to prune rather than risk losing commits.

    ``for-each-ref`` walks every ref, not just branches and tags, so a commit
    anchored only by ``refs/stash``, ``refs/remotes`` or ``refs/notes`` counts
    as contained. It does not see another worktree's detached HEAD, which is
    unreachable by this measure and therefore kept. Measured at 0.066s per call
    against 3269 refs.
    """
    if not head:
        return False
    try:
        found = run_git(["for-each-ref", "--contains", head, "--count=1", "--format=%(refname)"])
    except RuntimeError:
        return False
    return bool(found.strip())
