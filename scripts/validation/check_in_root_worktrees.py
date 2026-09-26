#!/usr/bin/env python3
"""Report git worktrees that live inside another checkout of the same repository.

`.claude/rules/universal.md` MUST NOT 6 requires worktrees to stay outside the
clone. Issue #4702 measured what happens when they do not. Agent worktrees were
created under `.claude/worktrees/` inside the repository root: 144 of 294 in
one clone, nested up to three deep
(`.claude/worktrees/a/.claude/worktrees/b/.claude/worktrees/c`). Every
recursive walk then multiplies its count by the number of live worktrees; one
scan returned 1,557,567 before excluding them. At least seven scanners carry
their own exclusion for this, and a new scanner that forgets one reports
inflated numbers with no error.

This check measures the condition itself, so a regression surfaces the day it
happens instead of as a wrong count months later.

TWO FINDINGS, TWO SOURCES. They do not overlap, which is why both run:

  * Registered: ``git worktree list --porcelain`` names every checkout. A
    worktree is in-root when its path sits inside any OTHER listed checkout,
    main or linked. Comparing against every checkout, not only the main one,
    catches the nested case the issue recorded.
  * Orphaned: a directory holding the `.git` file `git worktree add` writes,
    found inside this checkout, that git does not list. Issue #5111 showed
    the admin record can be pruned while the directory survives. A submodule
    also gets a `.git` file, but its `gitdir:` points under `.git/modules/`,
    so only a pointer under a `worktrees/` admin directory counts.

A registered worktree whose directory is gone is reported as missing, with
`git worktree prune` as the repair, because `git worktree move` needs the
directory.

Orphan scan scope is the direct children of the checkout root plus the direct
children of each container in ``CONTAINER_DIRS``. Those are the places
`.gitignore` already names as worktree homes (`.claude/worktrees/`,
`.worktrees/`, `.wt/`, and root-level `wt_*`, `worktree-*`, `.work-*`), plus
`.cache/worktrees/` from `check_shipped_skill_routes.py`. A full recursive
walk would descend into every nested checkout, which is the cost this check
exists to remove.

EXIT CODES (ADR-035):
  0 - no in-root worktrees (prints the examined count)
  1 - at least one worktree inside a checkout of this repository
  2 - configuration error (an explicit --repo-root that is not a directory)
  3 - external failure: `git worktree list` failed and the filesystem half
      found nothing, so the registered half is unproved, not clean
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_VALIDATION_DIR = Path(__file__).resolve().parent
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_tmp_worktrees import is_worktree_dir, parse_worktree_list  # noqa: E402

_GIT_TIMEOUT_SECONDS = 10

# Containers whose direct children are scanned for orphaned worktrees, relative
# to the checkout root. The root itself ("") covers root-level names such as
# `wt_*` and `worktree-*`.
CONTAINER_DIRS: tuple[str, ...] = (
    "",
    ".claude/worktrees",
    ".worktrees",
    ".wt",
    ".cache/worktrees",
)

RULE_CITATION = ".claude/rules/universal.md MUST NOT 6 (git worktrees MUST be external)"


@dataclass(frozen=True, slots=True)
class InRootWorktree:
    """One worktree found inside another checkout."""

    path: str
    parent: str
    registered: bool
    missing: bool = False


@dataclass
class InRootReport:
    """What one scan found. ``examined`` distinguishes a clean run from no run."""

    repo_root: str
    examined: int
    registered_count: int
    worktrees: list[InRootWorktree] = field(default_factory=list)
    git_listing_failed: bool = False
    unreadable_entries: int = 0

    @property
    def has_findings(self) -> bool:
        """True when at least one worktree sits inside a checkout."""
        return bool(self.worktrees)


def _resolve(raw: str) -> Path | None:
    """Resolve a path, or None when the filesystem cannot answer."""
    try:
        return Path(raw).resolve()
    except (OSError, RuntimeError):
        return None


def _exists(path: Path) -> bool:
    """True when ``path`` exists. An unanswerable stat counts as present."""
    try:
        return path.exists()
    except OSError:
        return True


def is_linked_worktree_dir(candidate: Path) -> bool:
    """True when ``candidate`` is a linked worktree, not a submodule.

    Both carry a `.git` file starting `gitdir:`. A linked worktree points at
    `<common dir>/worktrees/<name>`; a submodule points at
    `<superproject>/.git/modules/<name>`.
    """
    if not is_worktree_dir(candidate):
        return False
    try:
        with (candidate / ".git").open(encoding="utf-8", errors="replace") as handle:
            target = handle.readline()[len("gitdir:") :].strip()
    except OSError:
        return False
    return "/worktrees/" in target.replace("\\", "/")


def _innermost_parent(path: Path, checkouts: list[Path]) -> Path | None:
    """Return the deepest checkout that strictly contains ``path``, if any."""
    containing = [c for c in checkouts if c != path and path.is_relative_to(c)]
    if not containing:
        return None
    return max(containing, key=lambda c: len(c.parts))


def find_nested_registered(registered: list[str]) -> list[InRootWorktree]:
    """Return each registered worktree that sits inside another registered checkout.

    The parent named is the innermost one, so a worktree three levels deep is
    reported against the checkout that directly holds it.
    """
    resolved = [(raw, _resolve(raw)) for raw in registered]
    checkouts = [path for _, path in resolved if path is not None]
    found: list[InRootWorktree] = []
    for raw, path in resolved:
        if path is None:
            continue
        parent = _innermost_parent(path, checkouts)
        if parent is not None:
            found.append(
                InRootWorktree(
                    path=raw, parent=str(parent), registered=True, missing=not _exists(path)
                )
            )
    return found


def _list_registered(repo_root: Path) -> tuple[list[str], bool]:
    """Return (worktree paths, failed). A git failure is reported, never raised.

    Fail-open on the git half only. The filesystem half does not depend on git,
    so a git failure must not suppress an orphan finding.
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


def _child_dirs(container: Path, report: InRootReport) -> list[Path]:
    """Return the directories directly under ``container``; count what cannot be read."""
    try:
        if not container.is_dir():
            return []
        entries = sorted(container.iterdir())
    except OSError:
        report.unreadable_entries += 1
        return []
    children: list[Path] = []
    for entry in entries:
        try:
            if entry.is_dir():
                children.append(entry)
        except OSError:
            report.unreadable_entries += 1
    return children


def scan_repo_root(
    repo_root: Path,
    registered: list[str],
    git_listing_failed: bool,
) -> InRootReport:
    """Build the report for one checkout. Pure apart from filesystem reads."""
    report = InRootReport(
        repo_root=str(repo_root),
        examined=0,
        registered_count=len(registered),
        git_listing_failed=git_listing_failed,
    )
    report.worktrees.extend(find_nested_registered(registered))
    known = {path for path in (_resolve(raw) for raw in registered) if path is not None}

    for container in CONTAINER_DIRS:
        for entry in _child_dirs(repo_root / container, report):
            report.examined += 1
            if not is_linked_worktree_dir(entry) or _resolve(str(entry)) in known:
                continue
            report.worktrees.append(
                InRootWorktree(path=str(entry), parent=str(repo_root), registered=False)
            )
    return report


def build_report(repo_root: Path) -> InRootReport:
    """Run both halves of the scan against ``repo_root`` and return the report."""
    registered, git_listing_failed = _list_registered(repo_root)
    return scan_repo_root(repo_root, registered, git_listing_failed)


def _origin(worktree: InRootWorktree, git_listing_failed: bool) -> str:
    """Label one finding by what is known about it."""
    if worktree.missing:
        return "registered, directory missing; run git worktree prune"
    if worktree.registered:
        return "registered"
    if git_listing_failed:
        return "unverified (git listing failed)"
    return "orphaned (git does not know it)"


def format_report(report: InRootReport) -> str:
    """Render the human-readable report. Always names the examined count."""
    lines: list[str] = []
    if report.worktrees:
        lines.append(
            f"in-root-worktrees: {len(report.worktrees)} worktree(s) inside a checkout, "
            f"against {RULE_CITATION}:"
        )
        for worktree in report.worktrees:
            origin = _origin(worktree, report.git_listing_failed)
            lines.append(f"  {worktree.path} [{origin}, inside {worktree.parent}]")
        lines.append(
            "  Move each registered one with: git worktree move <path> <sibling path>. "
            "Harness default is .claude/worktrees/ (issue #4702)."
        )
    if report.git_listing_failed:
        lines.append(
            "in-root-worktrees: git worktree list failed; the registered half of this "
            "report is incomplete (the filesystem half still ran)."
        )
    if report.unreadable_entries:
        lines.append(
            f"in-root-worktrees: {report.unreadable_entries} entry/entries were "
            "unreadable and were not examined."
        )
    lines.append(
        f"in-root-worktrees: {len(report.worktrees)} in-root worktree(s) across "
        f"{report.registered_count} registered checkout(s) and {report.examined} "
        f"examined entries under {report.repo_root}"
    )
    return "\n".join(lines)


def validate_in_root_worktrees(repo_root: Path) -> bool:
    """Advisory pre-PR gate. Prints findings and always returns True.

    Advisory for the same reason as ``validate_tmp_worktrees``: the subject is
    machine state, not the diff. The harness that creates these worktrees is
    outside the repository, and the ones it leaves outlive the session that
    made them, so a blocking verdict would refuse every push on the machine for
    a condition the pushing agent did not create. The CLI below exits 1 on the
    same findings for anyone who wants the blocking form.
    """
    print(format_report(build_report(repo_root)))
    return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Report git worktrees that live inside a checkout of this repository.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Checkout to scan (default: the checkout holding this script).",
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
    if args.repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]
    else:
        repo_root = args.repo_root.resolve()
        if not repo_root.is_dir():
            print(f"error: --repo-root is not a directory: {args.repo_root}", file=sys.stderr)
            return 2

    report = build_report(repo_root)
    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(format_report(report))
    if report.has_findings:
        return 1
    return 3 if report.git_listing_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
