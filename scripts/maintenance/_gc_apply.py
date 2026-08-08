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
    heads = {decision.path: _head_of(decision.path, run_git) for decision in fresh.candidates}

    for decision in report.candidates:
        if decision.path not in still_safe:
            changed = fresh_reasons.get(decision.path, "no longer registered")
            report.remove_errors.append(
                f"{decision.path}: skipped, changed since the plan: {changed}"
            )
            continue
        moved = _head_moved_since(decision.path, heads.get(decision.path), run_git)
        if moved:
            report.remove_errors.append(f"{decision.path}: skipped, {moved}")
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
