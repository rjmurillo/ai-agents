#!/usr/bin/env python3
"""Garbage-collect stale git worktrees safely.

Agent and PR workflows create git worktrees that accumulate without cleanup.
Issue #2761 recorded 113 worktrees totalling 10.6G on one machine, which
starved the markdown language server (333,979 .md files under the workspace).
This tool reaps worktrees whose branch is fully pushed or merged, while
refusing to touch anything that could lose work.

A worktree is REMOVED only when EVERY safety condition holds:

  1. It is not the current or main worktree.
  2. It is not locked (``git worktree lock``).
  3. Its working tree is clean (``git status --porcelain`` empty).
  4. Its branch is fully pushed (no commits absent from every remote)
     OR its branch is merged into ``origin/main``.

A worktree that fails any condition is KEPT, and the reason is reported.

DEFAULT IS DRY-RUN. Nothing is removed unless ``--apply`` is passed. Dry-run
prints the removal candidates and the kept-with-reason list and exits without
mutating anything.

USAGE:
  # Preview what would be removed (safe, default):
  uv run python scripts/maintenance/gc_worktrees.py

  # Actually remove the safe candidates:
  uv run python scripts/maintenance/gc_worktrees.py --apply

  # Compare merge status against a different base:
  uv run python scripts/maintenance/gc_worktrees.py --base origin/main

  # Machine-readable output:
  uv run python scripts/maintenance/gc_worktrees.py --json

EXIT CODES:
  0 - Success (dry-run completed, or apply removed/kept as planned)
  2 - Apply ran, but one or more removals were withheld or failed
  3 - External: a git subprocess failed (for example, an unusable base ref)

See: ADR-035 Exit Code Standardization
Related: Issue #2761 (worktree accumulation starves markdown LSP), #2759
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

if TYPE_CHECKING:
    from scripts.maintenance import _gc_apply, _gc_parse, _gc_reasons, _gc_remote, _gc_stale
else:
    try:
        from scripts.maintenance import (
            _gc_apply,
            _gc_parse,
            _gc_reasons,
            _gc_remote,
            _gc_stale,
        )
    except ModuleNotFoundError:
        import _gc_apply
        import _gc_parse
        import _gc_reasons
        import _gc_remote
        import _gc_stale

from scripts.maintenance.worktree_occupancy import (  # noqa: E402
    Occupancy,
    is_occupied,
    occupied_paths,
)
from scripts.maintenance.worktree_report import (  # noqa: E402
    KEEP_ADMIN_ONLY,
    KEEP_BARE,
    KEEP_DETACHED,
    KEEP_DIRTY,
    KEEP_GIT_ERROR,
    KEEP_LOCKED,
    KEEP_MAIN,
    KEEP_OCCUPIED,
    KEEP_TIME_BUDGET,
    KEEP_UNPUSHED,
    Decision,
    GcReport,
    Worktree,
    format_report,
)

_DEFAULT_BASE = "origin/main"
_GIT_TIMEOUT_SECONDS = 10
_DECIDE_WORKERS = 8

# Inspecting one worktree costs up to three git subprocesses, so the wall clock
# grows with the worktree count while the caller's patience does not. The
# pre-push job that runs this reporter is capped by lefthook, and a kill there
# rejects the push even though this script only reports: a lefthook timeout
# kill cannot be swallowed by the job's own shell, unlike a non-zero exit,
# which the job's `|| echo` guard absorbs. That asymmetry is why these two
# constants must keep the worst case under the lefthook cap rather than lean
# on the guard. Issue 4257 rules out buying headroom by raising the cap, since
# that only moves the cliff and lengthens the block before a push dies. The cap
# itself lives in lefthook.yml; tests/ci/test_worktree_gc_wiring.py pins the
# two together so neither can drift into a push-rejecting pair. The budget is a
# bound on work attempted, not on elapsed time. See build_report for why.
_DEFAULT_TIME_BUDGET_SECONDS = 60.0


def _run_git(args: list[str], cwd: str | None = None) -> str:
    """Run a git command and return stripped stdout. Raises on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=cwd,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        location = f" in {cwd}" if cwd else ""
        raise RuntimeError(f"git {' '.join(args)}{location} failed: {exc}") from exc
    if result.returncode != 0:
        location = f" in {cwd}" if cwd else ""
        msg = f"git {' '.join(args)}{location} failed: {result.stderr.strip()}"
        raise RuntimeError(msg)
    return result.stdout.strip()


def has_uncommitted_changes(path: str) -> bool:
    """Return True when the worktree has staged or unstaged changes."""
    return bool(_run_git(["status", "--porcelain"], cwd=path))


def has_unpushed_commits(path: str) -> bool:
    """Return True when the branch has commits not present on any remote.

    ``git log HEAD --not --remotes`` lists commits reachable from this
    worktree's HEAD but from no remote-tracking ref. That scopes the result to
    this worktree's branch, not every local branch.
    """
    out = _run_git(
        ["log", "--format=%H", "HEAD", "--not", "--remotes"],
        cwd=path,
    )
    return bool(out)


def is_merged_to_base(path: str, base_ref: str) -> bool:
    """Return True when the worktree's HEAD is an ancestor of ``base_ref``.

    Uses ``git merge-base --is-ancestor`` (exit 0 = ancestor/merged,
    exit 1 = not). Any other exit is a real git error and propagates.
    """
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", "HEAD", base_ref],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=path,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"git merge-base in {path} failed: {exc}") from exc
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    msg = f"git merge-base in {path} failed: {result.stderr.strip()}"
    raise RuntimeError(msg)


def decide(
    worktree: Worktree,
    main_path: str,
    base_ref: str,
    *,
    current_path: str | None = None,
    inspect: bool = True,
    cwds: frozenset[str] = frozenset(),
    remote_head_refs: frozenset[str] | None = None,
    origin_upstreams: dict[str, str] | None = None,
    checkout_present: Callable[[str], bool] | None = None,
) -> Decision:
    """Decide whether a worktree is safe to remove. KEEP on any doubt.

    Order matters: cheap structural checks first, git-state checks last. A git
    inspection failure keeps the worktree (fail-safe), never removes it.

    ``inspect=False`` stops before the git-state checks and keeps the worktree
    with ``KEEP_TIME_BUDGET``. The structural checks above that point cost no
    subprocess, so they still run and still report the real reason. Detachment
    is not one of them: deciding a detached worktree needs its merge status, so
    it sits below the gate and a spent budget reports ``KEEP_TIME_BUDGET``
    rather than ``KEEP_DETACHED``. Both keep the worktree, so the fail-safe
    invariant holds either way.

    A stale worktree is always kept. Staleness is not ``prunable`` alone: git
    sets that marker only when the recorded directory is gone, and it computes
    it at all only for entries it would consider pruning. Three different
    situations produce a stale entry: the directory was deleted and abandoned,
    the directory was deleted while its index still held staged content, or the
    directory was **moved and is still in use**.
    Nothing in the admin record separates them, and removing the entry silently
    orphans staged blobs in the second case and breaks a live checkout in the
    third. So the report names the entry, lists everything clearing it would
    destroy, and stops there. ``git worktree repair <new-path>`` restores the
    moved case without losing anything; per-path ``git worktree remove <path>``
    clears the deleted case without touching any sibling.
    """
    protected_paths = {main_path}
    if current_path:
        protected_paths.add(current_path)
    if worktree.path in protected_paths or worktree.bare:
        reason = KEEP_BARE if worktree.bare else KEEP_MAIN
        return Decision(worktree.path, worktree.branch, remove=False, reason=reason)

    # Resolved here rather than as a default argument. A default binds the
    # probe at import, so a test that replaces the module attribute never
    # reaches it and quietly measures production behaviour instead.
    present = checkout_present or _gc_stale.linked_checkout_present

    def kept(reason: str) -> Decision:
        """Attach the stale-entry risk to whichever structural reason won.

        A locked or occupied entry that has lost its directory holds exactly
        the same at-risk index and reflog as any other stale entry. Returning
        the structural reason alone tells a reader who later unlocks it that
        there was nothing else to know, and clearing it then destroys the same
        work. The time-budget path is deliberately excluded: it exists to skip
        this work, and the report already discloses those entries as
        uninspected.

        Staleness here is not ``prunable`` alone, for the same reason it is not
        on the unlocked path. Verified against real git: git suppresses the
        ``prunable`` marker for a locked worktree even when its directory is
        gone, because it will not prune a locked entry regardless. So a missing
        or foreign checkout counts on its own. That check is two file reads and
        cannot fire on a healthy worktree, whose marker points back by
        definition.
        """
        if _gc_stale.is_stale(worktree, present):
            return Decision(
                worktree.path,
                worktree.branch,
                remove=False,
                reason=f"{reason}; {_gc_reasons.stale_keep_reason(worktree, main_path, _run_git)}",
            )
        return Decision(worktree.path, worktree.branch, remove=False, reason=reason)

    def removable(reason: str) -> Decision:
        """A removal, unless something in the worktree is still anchoring work.

        Clean, merged, and fully pushed all describe the current HEAD. They say
        nothing about commits the worktree reached and left, which its own
        reflog alone still names, and nothing about a suspended merge, rebase,
        cherry-pick, revert, or bisect, whose pseudo-ref is the only thing
        reaching the other side. Removing the entry deletes both. So the last
        questions asked before proposing a removal are whether anything is
        running here and whether the removal is provably lossless. An
        unreadable probe answers no.

        Both live here rather than earlier in ``decide`` because this is the
        one place a ``remove=True`` is constructed, which makes them impossible
        to bypass by reordering the checks above. The cost of that is a
        worktree kept for another reason reporting that other reason instead;
        the operation is only named when it would otherwise have been removed,
        which is the case that matters.
        """
        operation = _gc_stale.in_progress_operation(worktree.path)
        if operation is not None:
            reason = _gc_reasons.suspended_operation_reason(operation)
            return Decision(worktree.path, worktree.branch, remove=False, reason=reason)
        loss = _gc_reasons.reflog_only_work(worktree.path, main_path, _run_git)
        if not loss:
            return Decision(
                worktree.path,
                worktree.branch,
                remove=True,
                reason=reason,
                head=worktree.head,
            )
        return Decision(
            worktree.path,
            worktree.branch,
            remove=False,
            reason=f"{KEEP_ADMIN_ONLY} ({reason}); {loss}",
        )

    if worktree.locked:
        return kept(KEEP_LOCKED) if inspect else _keep(worktree, KEEP_LOCKED)

    if is_occupied(worktree.path, cwds):
        return kept(KEEP_OCCUPIED) if inspect else _keep(worktree, KEEP_OCCUPIED)

    if not inspect:
        return _keep(worktree, KEEP_TIME_BUDGET)

    if _gc_stale.is_stale(worktree, present):
        return Decision(
            worktree.path,
            worktree.branch,
            remove=False,
            reason=_gc_reasons.stale_keep_reason(worktree, main_path, _run_git),
        )

    try:
        if has_uncommitted_changes(worktree.path):
            return Decision(worktree.path, worktree.branch, remove=False, reason=KEEP_DIRTY)
        merged = is_merged_to_base(worktree.path, base_ref)
        reason = "merged to base"
        if worktree.detached or worktree.branch is None:
            if merged:
                return removable(reason)
            return Decision(worktree.path, worktree.branch, remove=False, reason=KEEP_DETACHED)
        if (
            not merged
            and remote_head_refs is not None
            and _gc_remote.is_merged_by_deleted_upstream(
                worktree.branch,
                remote_head_refs,
                origin_upstreams or {},
            )
        ):
            merged = True
            reason = "merged by deleted upstream"
        if not merged and has_unpushed_commits(worktree.path):
            return Decision(worktree.path, worktree.branch, remove=False, reason=KEEP_UNPUSHED)
    except RuntimeError:
        return Decision(worktree.path, worktree.branch, remove=False, reason=KEEP_GIT_ERROR)

    pushed = reason if merged else "fully pushed"
    return removable(pushed)


def _keep(worktree: Worktree, reason: str) -> Decision:
    """A kept decision with no further inspection attached."""
    return Decision(worktree.path, worktree.branch, remove=False, reason=reason)


def build_report(
    base_ref: str,
    apply: bool,
    *,
    time_budget: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    cwds: frozenset[str] | None = None,
) -> GcReport:
    """Inspect all worktrees and build the GC plan (no mutation here).

    ``time_budget`` bounds the inspection loop in seconds. Once it is spent,
    every remaining worktree is kept unread with ``KEEP_TIME_BUDGET`` rather
    than inspected. A budget of ``None`` or a non-positive number means
    unlimited. Keeping the leftovers preserves the fail-safe invariant: a
    worktree this run never looked at can never be proposed for removal.

    The budget is checked when a worker picks up a worktree, so it bounds how
    many are inspected, not the wall clock. Decisions run on a pool of
    ``_DECIDE_WORKERS`` threads, so up to that many inspections can be in
    flight when the deadline passes and the inspected set is not a strict
    prefix of the worktree list. Every value the workers read is fixed before
    the pool starts and none of them write shared state, so the concurrency
    adds no race; ``executor.map`` also returns in input order, so the report
    stays deterministic in ordering even though the cutoff is not.
    ``subprocess.run(timeout=...)`` starts its clock only once the child
    exists, so a loaded machine can stall in process creation for longer than
    the per-call cap. Treat the budget as a strong bound on work attempted and
    a soft one on elapsed time; size the caller's timeout with headroom rather
    than against an arithmetic sum.

    ``cwds`` overrides live-process detection, for tests. By default the working
    directories of running processes are read once and any worktree holding one
    is kept, because a clean, merged, fully pushed worktree can still be the
    home of a running agent.

    The deadline starts before any work, so the ``/proc`` scan and the two
    setup git calls are inside the budget rather than added to it. Overrunning
    during setup leaves every worktree uninspected, which is the fail-safe
    direction: an uninspected worktree can never be proposed for removal.
    """
    deadline = clock() + time_budget if time_budget and time_budget > 0 else None
    worktrees = _gc_parse.list_worktrees(_run_git)
    occupancy = Occupancy(cwds, 0, proc_available=True) if cwds is not None else occupied_paths()
    live_cwds = occupancy.cwds
    main_path = worktrees[0].path if worktrees else ""
    current_path = _run_git(["rev-parse", "--show-toplevel"])
    remote_head_refs: frozenset[str] | None
    remote_head_lookup_failed = False
    remote_head_lookup_error = None
    try:
        remote_head_refs = _gc_remote.load_remote_head_refs(_run_git)
    except RuntimeError as exc:
        remote_head_refs = None
        remote_head_lookup_failed = True
        remote_head_lookup_error = str(exc)
    origin_upstreams = (
        _gc_remote.try_load_origin_upstreams(_run_git) if remote_head_refs is not None else {}
    )
    report = GcReport(
        timestamp=datetime.now(UTC).isoformat(),
        base_ref=base_ref,
        apply=apply,
        main_worktree=main_path,
        total_worktrees=len(worktrees),
        occupancy_unreadable=occupancy.unreadable,
        occupancy_unavailable=not occupancy.proc_available,
        remote_head_lookup_failed=remote_head_lookup_failed,
        remote_head_lookup_error=remote_head_lookup_error,
    )

    def decide_one(worktree: Worktree) -> Decision:
        return decide(
            worktree,
            main_path,
            base_ref,
            current_path=current_path,
            inspect=deadline is None or clock() < deadline,
            cwds=live_cwds,
            remote_head_refs=remote_head_refs,
            origin_upstreams=origin_upstreams,
        )

    workers = min(_DECIDE_WORKERS, len(worktrees)) or 1
    with ThreadPoolExecutor(max_workers=workers) as executor:
        report.decisions = list(executor.map(decide_one, worktrees))
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Safely garbage-collect stale git worktrees (dry-run by default)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually remove safe candidates. Default is dry-run (no mutation).",
    )
    parser.add_argument(
        "--base",
        default=_DEFAULT_BASE,
        help=f"Base ref to test merge status against (default: {_DEFAULT_BASE}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the report as JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--time-budget",
        type=float,
        default=_DEFAULT_TIME_BUDGET_SECONDS,
        metavar="SECONDS",
        help=(
            "Stop inspecting after this many seconds and keep the remaining "
            "worktrees unread (default: %(default)s). Pass 0 for an unbounded "
            "pass. Uninspected worktrees are never removal candidates."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = parse_args(argv)
    try:
        report = build_report(base_ref=args.base, apply=args.apply, time_budget=args.time_budget)
        if args.apply:
            _gc_apply.apply_removals(
                report,
                lambda: build_report(report.base_ref, apply=True),
                _run_git,
            )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_report(report))
    if args.apply and report.remove_errors:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
