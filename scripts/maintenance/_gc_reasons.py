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

import os.path
import shlex
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
    KEEP_STALE_HEAD_UNKNOWN,
    KEEP_STALE_OCCUPIED,
    KEEP_STALE_UNREACHABLE,
    Worktree,
)

_GIT_TIMEOUT_SECONDS = 10


def _path_confirmed_absent(path: str) -> bool:
    """True only when ``path`` is confirmed missing, not merely unreadable.

    ``os.path.lexists()`` returns ``False`` for any ``OSError`` raised while
    probing the path, not only when the path is genuinely absent. A
    permission error or a transient I/O error on an occupied path would then
    read as "absent" and print the destructive ``git worktree remove``
    advice for a path that still exists and simply could not be stat'd. That
    recreates the "unreadable means absent" defect this module exists to
    close (issue #4718 review). Only ``FileNotFoundError`` confirms absence;
    every other ``OSError`` means occupied-or-unknown, so no removal command
    is printed.
    """
    try:
        os.lstat(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


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

    Every git call runs in the main worktree. The registered checkout is gone
    or has been replaced, which is what made the entry stale.
    """
    advice = KEEP_STALE if _path_confirmed_absent(worktree.path) else KEEP_STALE_OCCUPIED
    admin = _gc_stale.admin_dir_for(worktree.path, partial(run_git, cwd=main_path), main_path)
    if admin is None:
        head = _head_warning(worktree.head, main_path, run_git)
        lead = f"{head} | " if head else ""
        return (
            f"{lead}could not locate its admin entry, so nothing else about it "
            f"was checked; {advice}"
        )
    warnings = [
        _head_warning(worktree.head, main_path, run_git),
        _staged_warning(admin, worktree.head, main_path),
        _admin_warning(admin, main_path),
    ]
    lead = "".join(f"{warning} | " for warning in warnings if warning)
    return f"{lead}{advice}"


def reflog_only_work(worktree_path: str, main_path: str, run_git: Callable[..., str]) -> str:
    """What a healthy candidate would still lose, or "" when it would lose nothing.

    A worktree can be clean, merged, and fully pushed and still be the only
    thing anchoring a commit. Check a branch out, commit, check something else
    out: the commit is now named by nothing but that worktree's own reflog, and
    every ordinary check reports the entry as safe to remove. ``git worktree
    remove`` deletes the admin directory, the reflog goes with it, and the
    commit becomes unreachable.

    The stale path already probes for this. Running the same probe on healthy
    removal candidates is what stops the report from calling an entry safe when
    it is not. An unreadable probe answers "keep", because the question this
    asks is whether removal is provably lossless, and an unknown is not a no.
    """
    admin = _gc_stale.admin_dir_for(worktree_path, partial(run_git, cwd=main_path), main_path)
    if admin is None:
        return "its admin entry could not be located, so abandoned commits cannot be ruled out"
    return _admin_warning(admin, main_path)


def _head_warning(head: str | None, main_path: str, run_git: Callable[..., str]) -> str:
    """Whether clearing the entry abandons its detached HEAD.

    The rescue command runs in the main worktree. The stale entry's own
    directory is gone, so a bare ``git branch`` emitted here would run wherever
    the reader happens to stand, and outside any repository it fails with
    ``not a git repository`` while reading as the printed rescue. ``git -C``
    pins it to the repository whose object database still holds the commit.
    """
    if not head:
        return "its recorded HEAD is missing, so nothing about it could be rescued"
    reachable = stale_head_is_reachable(head, run_git)
    if reachable:
        return ""
    finding = KEEP_STALE_UNREACHABLE if reachable is False else KEEP_STALE_HEAD_UNKNOWN
    repo = shlex.quote(main_path)
    return f"WARNING: {finding}. Rescue first: git -C {repo} branch gc-rescue-{head} {head}"


def _staged_warning(admin: Path, head: str | None, main_path: str) -> str:
    """What the orphaned index holds, or why that could not be established."""
    if not head:
        return "its recorded HEAD is missing, so staged work cannot be ruled out"
    state = _gc_stale.staged_content_state(admin, head, main_path, _GIT_TIMEOUT_SECONDS)
    if state == _gc_stale.CLEAN:
        return ""
    if state == _gc_stale.UNKNOWN:
        return "its index could not be read, so staged work cannot be ruled out"
    index = shlex.quote(str(admin / "index"))
    repo = shlex.quote(main_path)
    return (
        "WARNING: its index holds staged work that no commit carries, and clearing the "
        f"entry deletes that index. Recover first: mkdir -p RECOVERY_DIR && "
        f"GIT_INDEX_FILE={index} git -C {repo} checkout-index -a "
        "--ignore-skip-worktree-bits --prefix=RECOVERY_DIR/ && "
        f"cp {index} RECOVERY_DIR/index | the copied index is the part that recovers "
        "everything: checkout-index writes only merged, non-submodule entries, and "
        "verified against real git it exits 0 while writing no files for an index of "
        "unmerged stages and an empty directory for a submodule entry, losing the "
        "recorded commit. It also creates RECOVERY_DIR only when it writes at least "
        "one file, so the mkdir is what lets the copy land in the very cases the copy "
        "exists for. Read the copy with "
        f"GIT_INDEX_FILE=RECOVERY_DIR/index git -C {repo} ls-files -s -u"
    )


def _admin_warning(admin: Path, main_path: str) -> str:
    """Which commits the admin directory alone anchors, or why that is unknown."""
    orphans = _gc_stale.unreachable_admin_commits(admin, main_path, _GIT_TIMEOUT_SECONDS)
    if orphans is None:
        return "its admin directory could not be read, so abandoned commits cannot be ruled out"
    if not orphans:
        return ""
    # Joined with && so a failed rescue stops the chain and shows in the exit code.
    # With ; or a bare space the later branches run anyway and the command as a whole
    # reports the last one's status, which reads as success while a commit stayed lost.
    # ``git -C`` pins every branch to the main worktree: the stale entry's own directory
    # is gone, so a bare ``git branch`` would run wherever the reader stands and fail
    # outside any repository while reading as the printed rescue.
    repo = shlex.quote(main_path)
    rescues = " && ".join(f"git -C {repo} branch gc-rescue-{sha} {sha}" for sha in orphans[:3])
    # Delimited with " | " rather than appended, the same way the staged-work
    # rescue separates its command from its prose. A reader copies from the
    # start of the chain to that delimiter, so text appended directly rides into
    # what they paste. Measured on the four-orphan case: with the note appended,
    # ``bash -c`` on the copied slice exits 2 with ``syntax error near
    # unexpected token `('`` and creates no rescue branch, so the sentence
    # counting the commits still at risk was what stopped the first three from
    # being rescued.
    more = (
        ""
        if len(orphans) <= 3
        else (
            f" | {len(orphans) - 3} more are named under "
            f"{shlex.quote(str(admin))}, which the removal deletes"
        )
    )
    return (
        f"WARNING: its admin directory is the only anchor for {len(orphans)} "
        f"commit(s), and clearing the entry deletes it. Rescue first: {rescues}{more}"
    )


def stale_head_is_reachable(head: str | None, run_git: Callable[..., str]) -> bool | None:
    """Is a stale worktree's HEAD still contained by some ref?

    Pruning a stale admin entry deletes the last ref that keeps a detached HEAD
    alive, so its commits become garbage-collectable. Every stale entry on this
    machine was contained when measured, but the tool must not assume that.

    Three-valued, because git has three answers. ``None`` means git refused or
    failed to answer. Both ``False`` and ``None`` keep the worktree, so the
    fail-safe direction is unchanged, but they are not the same sentence: the
    report used to state "no ref contains its HEAD" after a subprocess error,
    which asserts as a measured fact something nobody measured. A missing HEAD
    is ``False`` rather than unknown: there is no commit to contain.

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
        return None
    return bool(found.strip())


def suspended_operation_reason(operation: str) -> str:
    """Why a worktree in the middle of a git operation is not safe to remove."""
    return (
        f"{operation} here. Clearing the entry deletes the admin directory that "
        "holds it, along with any commit anchored only there. Finish it, abort "
        "it, or clear a lock a crashed git left behind, then re-run"
    )
