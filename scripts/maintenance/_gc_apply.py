#!/usr/bin/env python3
"""Act on a garbage-collection plan, after confirming the plan still holds.

Everything else in this tool only reads. This module is the only part that
mutates, which is why it lives apart: a reader auditing what can destroy work
has one file to audit.

A plan is a snapshot, so applying it is not a matter of replaying decisions.
The repository is re-read, each candidate's HEAD is re-checked immediately
before its own removal, and the first failure stops the run. ``revalidate`` is
a required argument rather than a default that reaches back for the report
builder: the caller owns which repository is being re-read, and a test that
forgets to supply one would otherwise scan the real machine.

Related: Issue #2761 (worktree accumulation starves the markdown LSP).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from scripts.maintenance import _gc_reasons, _gc_stale
from scripts.maintenance.worktree_report import GcReport


def remove_worktree(path: str, run_git: Callable[..., str]) -> None:
    """Remove a worktree via ``git worktree remove``. Raises on failure."""
    run_git(["worktree", "remove", path])


def apply_removals(
    report: GcReport, revalidate: Callable[[], GcReport], run_git: Callable[..., str]
) -> None:
    """Remove the candidates the plan named, after confirming they still qualify.

    A plan is a snapshot. Between building it and applying it a worktree can
    take a new commit, get locked, pick up uncommitted work, or acquire a live
    process, and the plan cannot know. Removing a detached worktree that
    committed in that window orphans the new commit, which is exactly the loss
    the reachability checks exist to prevent.

    So this rebuilds the report and removes only paths both runs propose. The
    fresh run re-answers every safety question with current data, which is why
    no check is duplicated here: a worktree that changed underneath the plan
    simply stops being a candidate. Anything the reviewed plan named but the
    fresh one does not is skipped with the fresh reason recorded, so the log
    says what changed rather than only that something did.

    Removal stops at the first failure. ``git worktree remove`` is not atomic:
    with the admin directory unwritable it deletes the working directory and
    then exits non-zero, leaving a half-removed entry. One failure means the
    repository is in a state this run did not predict, and the usual causes,
    permissions on the admin directory or a lock, apply to every later removal
    too. Continuing would turn one unexplained state into many.

    The recheck is a snapshot too, so each candidate's HEAD is read again
    immediately before its own removal. Removals run in series, so the last
    candidate in a long list would otherwise be acting on a reading taken
    seconds earlier, and a commit landing in that window is exactly what
    ``git worktree remove`` will not refuse: it rejects a dirty tree, and
    committing makes the tree clean. The window cannot be closed, only narrowed
    to a single git call, and a HEAD that moved inside it is skipped rather
    than removed.

    A HEAD comparison is not enough on its own, for two reasons found by
    review. The value it compares against has to be the one the recheck
    actually decided on, which is why each candidate carries it: reading the
    HEADs after the recheck returned meant a commit landing between the two
    reads became the expected value and then matched itself. And a worktree can
    commit and go back: check out a branch, commit, reset, and HEAD ends where
    it started while the commit survives with nothing but that worktree's
    reflog naming it. No comparison of HEAD against HEAD can see that one.

    The suspended-operation probe is run again here too, for the same reason
    and against the same window. A ``git merge --no-commit`` started after the
    recheck moves no HEAD and writes no reflog entry, so neither check above
    can see it, and the commit it holds is anchored only by a pseudo-ref inside
    the directory about to be deleted. The probe costs two file reads and no
    subprocess, so closing this window is nearly free.

    So the reflog probe is run again for each candidate immediately before its
    own removal, after the HEAD check. It asks the question that actually
    matters, whether removing this entry orphans a commit, against the
    repository as it is at that instant rather than as the plan found it. It
    costs one admin-directory lookup and one ``rev-list`` per candidate, and
    only for candidates that got that far. It cannot replace the HEAD check:
    ``rev-list --not --all`` examines every worktree's HEAD, so a commit that
    is still this worktree's own HEAD reads as reachable right up until the
    removal destroys the thing making it so. For the same reason the HEAD check
    cannot precede the probe alone: a commit landing while the probe's
    subprocess runs passes the earlier HEAD read and then reads as reachable to
    the probe, so the HEAD is read a second time after the probe returns, and a
    move seen only then withholds the removal.

    The checkout identity is re-read last, against the same window. Removals run
    in series, so between the recheck and this candidate's turn the directory at
    its path can be deleted and replaced, or another worktree can be moved onto
    it. ``git worktree remove`` names a path, so it would then act on whatever
    now sits there rather than on the entry the plan reviewed. The recheck
    excluded that at plan time, but only as the plan found it; re-asking here
    costs two file reads and skips the candidate when the checkout at its path
    is no longer the one the entry records.

    Refuses to mutate anything when either report is partial. A truncated run
    inspects whichever worktrees the clock allowed, so applying it would remove
    a different set than the dry run a reader reviewed. Rerun with
    ``--time-budget 0`` to get a complete, reviewable plan.

    Refuses just as hard when the occupancy scan was unavailable. A failed
    ``/proc`` read yields an empty set of process working directories, and an
    empty set is indistinguishable from "every worktree is vacant" at the point
    ``is_occupied`` consults it. Every worktree then clears the occupancy check
    on no evidence, so applying the plan can delete a directory a live process
    is sitting in. The dry run stays useful because the report discloses the
    gap; only the mutation is withheld.
    """
    if _refuses_to_mutate(report, report.remove_errors, "the plan"):
        return

    if not report.candidates:
        return

    fresh = revalidate()
    if _refuses_to_mutate(fresh, report.remove_errors, "the recheck"):
        return

    still_safe = {decision.path: decision for decision in fresh.candidates}
    fresh_reasons = {decision.path: decision.reason for decision in fresh.decisions}

    for decision in report.candidates:
        if decision.path not in still_safe:
            changed = fresh_reasons.get(decision.path, "no longer registered")
            report.remove_errors.append(
                f"{decision.path}: skipped, changed since the plan: {changed}"
            )
            continue
        moved = _head_moved_since(decision.path, still_safe[decision.path].head, run_git)
        if moved:
            report.remove_errors.append(f"{decision.path}: skipped, {moved}")
            continue
        orphaned = _gc_reasons.reflog_only_work(decision.path, fresh.main_worktree, run_git)
        if orphaned:
            report.remove_errors.append(f"{decision.path}: skipped, {orphaned}")
            continue
        # The reflog probe runs a subprocess, and a commit can land while it
        # does. That commit stays this worktree's HEAD, so the probe's own
        # ``rev-list --not --all`` reads it as reachable and reports no orphan,
        # and the HEAD check above already passed before the commit existed.
        # Re-reading HEAD here is what catches it; without this second read the
        # removal would delete the only thing anchoring that commit.
        moved_during_probe = _head_moved_since(
            decision.path, still_safe[decision.path].head, run_git
        )
        if moved_during_probe:
            report.remove_errors.append(
                f"{decision.path}: skipped, {moved_during_probe}, seen only after the reflog probe"
            )
            continue
        operation = _gc_stale.in_progress_operation(decision.path)
        if operation is not None:
            report.remove_errors.append(f"{decision.path}: skipped, {operation} since the recheck")
            continue
        if not _gc_stale.linked_checkout_present(decision.path):
            report.remove_errors.append(
                f"{decision.path}: skipped, its checkout is no longer the one "
                "registered at that path since the recheck"
            )
            continue
        try:
            remove_worktree(decision.path, run_git)
        except RuntimeError as exc:
            report.remove_errors.append(
                f"{decision.path}: {exc}; git worktree remove is not atomic, so this "
                "path may be half-removed. Stopping before the remaining "
                f"{len(report.candidates) - len(report.removed) - 1} candidate(s)."
            )
            return
        report.removed.append(decision.path)


def _head_of(path: str, run_git: Callable[..., str]) -> str | None:
    """The commit ``path`` is on right now, or ``None`` if git will not say."""
    try:
        return run_git(["rev-parse", "HEAD"], cwd=path)
    except RuntimeError:
        return None


def _head_moved_since(path: str, expected: str | None, run_git: Callable[..., str]) -> str:
    """Describe how ``path``'s HEAD differs from the recheck, or "" if it does not.

    Any answer other than "same commit" withholds the removal. An unreadable
    HEAD is not evidence of safety, and a recheck that recorded no HEAD leaves
    nothing to compare against.
    """
    if not expected:
        return "the recheck recorded no HEAD for it, so nothing confirms it is unchanged"
    current = _head_of(path, run_git)
    if current is None:
        return "its HEAD could not be read just before removal"
    if current != expected:
        return f"its HEAD moved from {expected} to {current} after the recheck"
    return ""


def _refuses_to_mutate(report: GcReport, errors: list[str], label: str) -> bool:
    """Record why ``report`` cannot be acted on, or return False if it can."""
    if report.occupancy_unavailable:
        errors.append(
            f"refused: {label} could not read /proc, so no worktree was checked "
            "for a live process; rerun where /proc is readable before applying"
        )
        return True
    if report.unevaluated:
        errors.append(
            f"refused: {len(report.unevaluated)} worktree(s) in {label} were not "
            "inspected; rerun with --time-budget 0 for a complete plan before applying"
        )
        return True
    return False
