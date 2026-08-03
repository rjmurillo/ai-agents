#!/usr/bin/env python3
"""The garbage-collection data model and how it renders.

Holds the decision record, the report that aggregates decisions, the stable
reason strings that tests and automation match on, and the human-readable
rendering. Separated from ``gc_worktrees.py`` so that deciding what is safe to
remove does not share a module with describing it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

# Reasons a worktree is kept (never removed). Stable strings for tests/automation.
KEEP_MAIN = "main-or-current worktree"
KEEP_BARE = "bare worktree"
KEEP_LOCKED = "locked"
KEEP_DIRTY = "uncommitted changes"
KEEP_DETACHED = "detached HEAD (no branch to evaluate)"
KEEP_UNPUSHED = "unpushed commits and not merged to base"
KEEP_GIT_ERROR = "git inspection failed"
KEEP_TIME_BUDGET = "not inspected (time budget exhausted)"
KEEP_OCCUPIED = "in use by a running process"


@dataclass
class Worktree:
    """A single registered git worktree parsed from porcelain output."""

    path: str
    branch: str | None = None
    head: str | None = None
    locked: bool = False
    bare: bool = False
    detached: bool = False


@dataclass
class Decision:
    """The GC decision for one worktree."""

    path: str
    branch: str | None
    remove: bool
    reason: str

    @property
    def kept(self) -> bool:
        """True when this worktree is kept rather than removed."""
        return not self.remove


@dataclass
class GcReport:
    """Complete garbage-collection plan across all worktrees."""

    timestamp: str
    base_ref: str
    apply: bool
    main_worktree: str
    total_worktrees: int = 0
    occupancy_unreadable: int = 0
    occupancy_unavailable: bool = False
    decisions: list[Decision] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    remove_errors: list[str] = field(default_factory=list)
    remote_head_lookup_failed: bool = False
    remote_head_lookup_error: str | None = None

    @property
    def candidates(self) -> list[Decision]:
        """Decisions marked for removal."""
        return [d for d in self.decisions if d.remove]

    @property
    def kept(self) -> list[Decision]:
        """Decisions kept with a reason."""
        return [d for d in self.decisions if d.kept]

    @property
    def needs_disposition(self) -> list[Decision]:
        """Kept branches that need a human disposition before they can shrink."""
        return [d for d in self.kept if d.reason == KEEP_UNPUSHED]

    @property
    def unevaluated(self) -> list[Decision]:
        """Worktrees the time budget stopped this run from inspecting."""
        return [d for d in self.decisions if d.reason == KEEP_TIME_BUDGET]


def _append_decision_group(
    lines: list[str],
    title: str,
    decisions: list[Decision],
    formatter: Callable[[Decision], str],
) -> None:
    """Append a titled decision group when there is anything to report."""
    if not decisions:
        return
    lines.append(title)
    for decision in decisions:
        lines.append(formatter(decision))


def _append_disposition_group(lines: list[str], decisions: list[Decision]) -> None:
    """Append kept branches that need human cleanup disposition."""
    if not decisions:
        return
    lines.append("  Needs disposition:")
    lines.append("    Review branch and issue state, then push, merge, lock, or delete.")
    for decision in decisions:
        lines.append(f"    - {decision.path} [{decision.branch}] unpushed and unmerged")


def _append_apply_result(lines: list[str], report: GcReport) -> None:
    """Append removal results from apply mode."""
    lines.append(f"  removed: {len(report.removed)}")
    for path in report.removed:
        lines.append(f"    - removed {path}")
    if report.remove_errors:
        lines.append(f"  errors: {len(report.remove_errors)}")
        for err in report.remove_errors:
            lines.append(f"    - {err}")


def format_report(report: GcReport) -> str:
    """Human-readable summary of the GC plan or result."""
    mode = "APPLY" if report.apply else "DRY-RUN"
    lines = [
        f"Worktree GC [{mode}] base={report.base_ref}",
        f"  total worktrees: {report.total_worktrees}",
        f"  removal candidates: {len(report.candidates)}",
        f"  kept: {len(report.kept)}",
    ]
    if report.remote_head_lookup_failed:
        lines.append("  remote head lookup failed, using ancestry-only merge checks")
        if report.remote_head_lookup_error:
            lines.append(f"    {report.remote_head_lookup_error}")
    if report.occupancy_unavailable:
        lines.append(
            "  occupancy check unavailable: /proc could not be read, so no "
            "worktree was checked for a live process. Every worktree below is "
            "reported without occupancy evidence."
        )
    if report.occupancy_unreadable:
        lines.append(
            f"  occupancy blind spot: {report.occupancy_unreadable} live "
            f"process(es) owned by this user would not report a working "
            f"directory, so they were not checked against any worktree."
        )
    if report.unevaluated:
        lines.append(
            f"  PARTIAL: time budget stopped this run after inspecting "
            f"{report.total_worktrees - len(report.unevaluated)} of "
            f"{report.total_worktrees}; the remaining {len(report.unevaluated)} "
            f"are kept unread. Raise --time-budget (0 disables) for a full pass."
        )
    _append_decision_group(
        lines,
        "  Candidates:",
        report.candidates,
        lambda d: f"    - {d.path} [{d.branch}] ({d.reason})",
    )
    _append_disposition_group(lines, report.needs_disposition)
    _append_decision_group(
        lines,
        "  Kept:",
        report.kept,
        lambda d: f"    - {d.path} [{d.branch}] KEEP: {d.reason}",
    )
    if report.apply:
        _append_apply_result(lines, report)
    else:
        lines.append(
            f"  DRY-RUN: removed nothing. Pass --apply to remove "
            f"{len(report.candidates)} candidate(s)."
        )
    return "\n".join(lines)
