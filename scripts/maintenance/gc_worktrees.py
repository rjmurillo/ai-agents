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
  2 - Error: configuration or runtime error (git failure, bad base ref)

See: ADR-035 Exit Code Standardization
Related: Issue #2761 (worktree accumulation starves markdown LSP), #2759
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.maintenance import _gc_remote
else:
    try:
        from scripts.maintenance import _gc_remote
    except ModuleNotFoundError:
        import _gc_remote

_DEFAULT_BASE = "origin/main"
_GIT_TIMEOUT_SECONDS = 30
_DECIDE_WORKERS = 8

# Reasons a worktree is kept (never removed). Stable strings for tests/automation.
KEEP_MAIN = "main-or-current worktree"
KEEP_BARE = "bare worktree"
KEEP_LOCKED = "locked"
KEEP_DIRTY = "uncommitted changes"
KEEP_DETACHED = "detached HEAD (no branch to evaluate)"
KEEP_UNPUSHED = "unpushed commits and not merged to base"
KEEP_GIT_ERROR = "git inspection failed"


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


def _apply_attribute(worktree: Worktree, line: str) -> None:
    """Apply one porcelain attribute line to the current worktree record.

    ``HEAD``, ``branch``, ``bare``, ``detached``, and ``locked`` are the lines
    that may follow a ``worktree <path>`` line. Unknown lines are ignored.
    """
    if line.startswith("HEAD "):
        worktree.head = line[len("HEAD ") :].strip()
    elif line.startswith("branch "):
        worktree.branch = line[len("branch ") :].strip().removeprefix("refs/heads/")
    elif line == "bare":
        worktree.bare = True
    elif line == "detached":
        worktree.detached = True
    elif line == "locked" or line.startswith("locked "):
        worktree.locked = True


def list_worktrees() -> list[Worktree]:
    """Parse ``git worktree list --porcelain`` into Worktree records.

    The porcelain format groups attributes per worktree, separated by blank
    lines. Each group starts with a ``worktree <path>`` line; attribute lines
    follow and are applied by ``_apply_attribute``.
    """
    raw = _run_git(["worktree", "list", "--porcelain"])
    worktrees: list[Worktree] = []
    current: Worktree | None = None

    for line in raw.splitlines():
        if line.startswith("worktree "):
            if current is not None:
                worktrees.append(current)
            current = Worktree(path=line[len("worktree ") :].strip())
        elif current is not None:
            _apply_attribute(current, line)

    if current is not None:
        worktrees.append(current)
    return worktrees


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
    remote_head_refs: frozenset[str] | None = None,
    origin_upstreams: dict[str, str] | None = None,
) -> Decision:
    """Decide whether a worktree is safe to remove. KEEP on any doubt.

    Order matters: cheap structural checks first, git-state checks last. A git
    inspection failure keeps the worktree (fail-safe), never removes it.
    """
    protected_paths = {main_path}
    if current_path:
        protected_paths.add(current_path)
    if worktree.path in protected_paths or worktree.bare:
        reason = KEEP_BARE if worktree.bare else KEEP_MAIN
        return Decision(worktree.path, worktree.branch, remove=False, reason=reason)

    if worktree.locked:
        return Decision(worktree.path, worktree.branch, remove=False, reason=KEEP_LOCKED)

    try:
        if has_uncommitted_changes(worktree.path):
            return Decision(worktree.path, worktree.branch, remove=False, reason=KEEP_DIRTY)
        merged = is_merged_to_base(worktree.path, base_ref)
        reason = "merged to base"
        if worktree.detached or worktree.branch is None:
            if merged:
                return Decision(worktree.path, worktree.branch, remove=True, reason=reason)
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
    return Decision(worktree.path, worktree.branch, remove=True, reason=pushed)


def remove_worktree(path: str) -> None:
    """Remove a worktree via ``git worktree remove``. Raises on failure."""
    _run_git(["worktree", "remove", path])


def prune_worktrees() -> str:
    """Prune dead worktree admin entries. Returns git's stdout (may be empty)."""
    return _run_git(["worktree", "prune", "-v"])


def build_report(base_ref: str, apply: bool) -> GcReport:
    """Inspect all worktrees and build the GC plan (no mutation here)."""
    worktrees = list_worktrees()
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
        remote_head_lookup_failed=remote_head_lookup_failed,
        remote_head_lookup_error=remote_head_lookup_error,
    )

    def decide_one(wt: Worktree) -> Decision:
        return decide(
            wt,
            main_path,
            base_ref,
            current_path=current_path,
            remote_head_refs=remote_head_refs,
            origin_upstreams=origin_upstreams,
        )

    workers = min(_DECIDE_WORKERS, len(worktrees)) or 1
    with ThreadPoolExecutor(max_workers=workers) as executor:
        report.decisions = list(executor.map(decide_one, worktrees))
    return report


def apply_removals(report: GcReport) -> None:
    """Remove the candidate worktrees, then prune admin entries.

    Records each success in ``report.removed`` and each failure in
    ``report.remove_errors`` without aborting the batch. Pruning runs once
    after removals to clean up any orphaned admin entries.
    """
    for decision in report.candidates:
        try:
            remove_worktree(decision.path)
            report.removed.append(decision.path)
        except RuntimeError as exc:
            report.remove_errors.append(f"{decision.path}: {exc}")
    try:
        prune_worktrees()
    except RuntimeError as exc:
        report.remove_errors.append(f"prune: {exc}")


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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = parse_args(argv)
    try:
        report = build_report(base_ref=args.base, apply=args.apply)
        if args.apply:
            apply_removals(report)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_report(report))
    if args.apply and report.remove_errors:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
