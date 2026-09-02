#!/usr/bin/env python3
"""Report git worktrees living under the system temp directory, and a low temp floor.

`.claude/rules/universal.md` MUST NOT 6 states the binding rule verbatim:

    6. Git worktrees MUST be external.

`.serena/memories/git/git-worktree-tmp-not-durable.md` carries the loss: a
four-conflict resolution for PR #4003 was committed to `/tmp/wt_4003`, `/tmp`
was reclaimed mid-session, and roughly two hours of work went with it because a
worktree's commits live only in that worktree's own object store until a push
lands.

Issue #5111 is the aggregate version of the same failure. Six orphaned
worktrees, `baseline_check`, and 33 pytest scratch directories filled a 16G
tmpfs to 4.0K free. Agent transcript writes then failed with ENOSPC, a
backgrounded `git push` failed while its wrapper reported exit 0, and five
commits believed pushed were not. The rule and the memory both already existed;
nothing measured the filesystem, so six violations accumulated unseen.

TWO FINDINGS, TWO SOURCES. They do not overlap, which is why both run:

  * Registered worktrees come from ``git worktree list --porcelain``.
  * Orphaned worktrees come from the filesystem. Issue #5111 recorded that
    ``git worktree list`` showed zero entries under `/tmp` while six worktree
    directories sat there, because the admin records had already been pruned.
    A directory is counted as a worktree when it holds a `.git` FILE whose
    first line begins `gitdir:`, which is what `git worktree add` writes. A
    `.git` DIRECTORY is an ordinary clone, not a worktree, and is not reported.

Scan depth is the immediate children of the temp root. Every worktree in the
issue's measurement sat at that depth (`/tmp/pr5010-work`, `/tmp/pr5025-worktree`,
and four siblings), and one level costs one `stat` per entry.

EXIT CODES (ADR-035):
  0 - no findings (prints the examined count)
  1 - at least one worktree under the temp root, or free space below the floor
  2 - configuration error (unusable argument, or an explicitly named temp root
      that does not exist)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

# 16G tmpfs is the machine in issue #5111. Two GiB is roughly one pytest
# scratch generation plus one worktree of headroom, so the report fires while
# there is still room to act rather than after a push has already died.
DEFAULT_MIN_FREE_GIB = 2.0
DEFAULT_TEMP_ROOT = Path("/tmp")
_BYTES_PER_GIB = 1024**3
_GIT_TIMEOUT_SECONDS = 10

RULE_CITATION = ".claude/rules/universal.md MUST NOT 6 (git worktrees MUST be external)"


@dataclass(frozen=True, slots=True)
class TempWorktree:
    """One worktree directory found under the temp root."""

    path: str
    registered: bool


@dataclass
class TempReport:
    """What one scan found. ``examined`` distinguishes a clean run from no run."""

    temp_root: str
    temp_root_present: bool
    examined: int
    free_bytes: int | None
    min_free_bytes: int
    worktrees: list[TempWorktree] = field(default_factory=list)
    git_listing_failed: bool = False
    unreadable_entries: int = 0

    @property
    def free_space_low(self) -> bool:
        """True when the temp root reported less free space than the floor."""
        return self.free_bytes is not None and self.free_bytes < self.min_free_bytes

    @property
    def has_findings(self) -> bool:
        """True when anything in this report should block or warn."""
        return bool(self.worktrees) or self.free_space_low


def parse_worktree_list(porcelain: str) -> list[str]:
    """Return the worktree paths in ``git worktree list --porcelain`` output.

    Empty or whitespace-only input returns an empty list: a repository with no
    linked worktrees is a normal state, not an error.
    """
    paths: list[str] = []
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            paths.append(line[len("worktree ") :].strip())
    return paths


def is_worktree_dir(candidate: Path) -> bool:
    """True when ``candidate`` holds the `.git` file `git worktree add` writes.

    A linked worktree gets a `.git` FILE containing `gitdir: <admin path>`. A
    plain clone gets a `.git` DIRECTORY. Only the first is a worktree, so a
    clone parked in the temp root is not reported as one.
    """
    marker = candidate / ".git"
    try:
        if not marker.is_file():
            return False
        with marker.open(encoding="utf-8", errors="replace") as handle:
            first_line = handle.readline()
    except OSError:
        return False
    return first_line.startswith("gitdir:")


def find_registered_temp_worktrees(paths: list[str], temp_root: Path) -> list[str]:
    """Return the registered worktree paths that sit under ``temp_root``."""
    found: list[str] = []
    for raw in paths:
        try:
            resolved = Path(raw).resolve()
        except OSError:
            continue
        if resolved.is_relative_to(temp_root):
            found.append(raw)
    return found


def _list_registered(repo_root: Path) -> tuple[list[str], bool]:
    """Return (worktree paths, failed). A git failure is reported, never raised.

    Fail-open on the git half only. The filesystem half below does not depend
    on git, so a git failure must not suppress the orphan finding that issue
    #5111 showed is the one git cannot see anyway.
    """
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=repo_root,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [], True
    if result.returncode != 0:
        return [], True
    return parse_worktree_list(result.stdout), False


def _is_directory(path: Path) -> bool | None:
    """True or False, or None when the filesystem could not answer.

    Three states, not two. A directory that cannot be read is not the same as
    one that is absent, and collapsing them would let an unreadable temp root
    report as a clean scan.
    """
    try:
        return path.is_dir()
    except OSError:
        return None


def scan_temp_root(
    temp_root: Path,
    min_free_bytes: int,
    registered: list[str],
    git_listing_failed: bool,
) -> TempReport:
    """Build the report for one temp root. Pure apart from filesystem reads."""
    root_state = _is_directory(temp_root)
    report = TempReport(
        temp_root=str(temp_root),
        temp_root_present=root_state is True,
        examined=0,
        free_bytes=None,
        min_free_bytes=min_free_bytes,
        git_listing_failed=git_listing_failed,
        unreadable_entries=1 if root_state is None else 0,
    )
    if not report.temp_root_present:
        return report

    registered_resolved = set(find_registered_temp_worktrees(registered, temp_root))
    seen: set[str] = set()
    try:
        entries = sorted(temp_root.iterdir())
    except OSError:
        report.unreadable_entries += 1
        entries = []

    for entry in entries:
        entry_state = _is_directory(entry)
        if entry_state is None:
            report.unreadable_entries += 1
            continue
        if not entry_state:
            continue
        report.examined += 1
        if not is_worktree_dir(entry):
            continue
        seen.add(str(entry))
        report.worktrees.append(
            TempWorktree(path=str(entry), registered=str(entry) in registered_resolved)
        )

    # A registered worktree whose directory is already gone still names a path
    # under the temp root, and its admin record is still work git can restore.
    # Report it even though the filesystem pass could not see it.
    for path in sorted(registered_resolved - seen):
        report.worktrees.append(TempWorktree(path=path, registered=True))

    try:
        report.free_bytes = shutil.disk_usage(temp_root).free
    except OSError:
        report.free_bytes = None
    return report


def build_report(
    repo_root: Path,
    temp_root: Path | None = None,
    min_free_gib: float = DEFAULT_MIN_FREE_GIB,
) -> TempReport:
    """Run both halves of the scan and return the combined report.

    ``temp_root`` resolves from the module attribute at call time rather than
    as a default argument. A default binds at import, so a test that replaces
    ``DEFAULT_TEMP_ROOT`` would never reach it and would quietly measure the
    real `/tmp` instead of its fixture. ``gc_worktrees.decide`` documents the
    same trap for the same reason.
    """
    registered, git_listing_failed = _list_registered(repo_root)
    return scan_temp_root(
        temp_root if temp_root is not None else DEFAULT_TEMP_ROOT,
        int(min_free_gib * _BYTES_PER_GIB),
        registered,
        git_listing_failed,
    )


def format_report(report: TempReport) -> str:
    """Render the human-readable report. Always names the examined count."""
    lines: list[str] = []
    if not report.temp_root_present:
        lines.append(f"tmp-worktrees: {report.temp_root} is not a directory; nothing examined")
        return "\n".join(lines)

    for worktree in report.worktrees:
        origin = "registered" if worktree.registered else "orphaned (git does not know it)"
        lines.append(f"  {worktree.path} [{origin}]")
    if report.worktrees:
        lines.insert(
            0,
            f"tmp-worktrees: {len(report.worktrees)} worktree(s) under {report.temp_root}, "
            f"against {RULE_CITATION}:",
        )
        lines.append("  Move each one with: git worktree move <path> <external path>")

    if report.free_space_low and report.free_bytes is not None:
        lines.append(
            f"tmp-worktrees: {report.temp_root} has "
            f"{report.free_bytes / _BYTES_PER_GIB:.2f} GiB free, below the "
            f"{report.min_free_bytes / _BYTES_PER_GIB:.2f} GiB floor. A full temp "
            "filesystem fails transcript writes and backgrounded pushes with ENOSPC "
            "(issue #5111)."
        )

    if report.git_listing_failed:
        lines.append(
            "tmp-worktrees: git worktree list failed; the registered half of this "
            "report is incomplete (the filesystem half still ran)."
        )
    if report.unreadable_entries:
        lines.append(
            f"tmp-worktrees: {report.unreadable_entries} entry/entries under "
            f"{report.temp_root} were unreadable and were not examined."
        )

    free_note = (
        f"{report.free_bytes / _BYTES_PER_GIB:.2f} GiB free"
        if report.free_bytes is not None
        else "free space unreadable"
    )
    lines.append(
        f"tmp-worktrees: {len(report.worktrees)} worktree(s) in "
        f"{report.examined} examined entries under {report.temp_root}; {free_note}"
    )
    return "\n".join(lines)


def validate_tmp_worktrees(repo_root: Path) -> bool:
    """Advisory pre-PR gate. Prints findings and always returns True.

    Advisory on purpose, and the reason is the incident itself. The subject is
    machine state, not repository state: the residue issue #5111 measured was
    left by sessions that had already ended, so a blocking verdict would refuse
    every push on that machine for a condition the current diff did not create
    and the pushing agent may not own. That is the same class of wedge the
    issue is about. The CLI below exits 1 on the same findings, so anyone who
    wants the blocking form has it without this gate imposing it on everyone.
    """
    report = build_report(repo_root)
    print(format_report(report))
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Report git worktrees under the temp root and low temp free space.",
    )
    parser.add_argument(
        "--temp-root",
        type=Path,
        default=DEFAULT_TEMP_ROOT,
        help=f"Directory to scan (default: {DEFAULT_TEMP_ROOT}).",
    )
    parser.add_argument(
        "--min-free-gib",
        type=float,
        default=DEFAULT_MIN_FREE_GIB,
        help=f"Free-space floor in GiB (default: {DEFAULT_MIN_FREE_GIB}).",
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
    if args.min_free_gib < 0:
        print("error: --min-free-gib must not be negative", file=sys.stderr)
        return 2

    temp_root = args.temp_root.resolve()
    explicit_root = args.temp_root != DEFAULT_TEMP_ROOT
    if explicit_root and not temp_root.is_dir():
        print(f"error: --temp-root is not a directory: {args.temp_root}", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[2]
    report = build_report(repo_root, temp_root, args.min_free_gib)

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_report(report))
    return 1 if report.has_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
