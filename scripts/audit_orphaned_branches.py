#!/usr/bin/env python3
"""Audit remote branches for orphaned session and memory artifacts.

Compares remote branches against main to find branches containing
session logs or memory files that were never merged. Produces a
structured JSON report for automation and a human-readable summary.

EXIT CODES:
  0 - Success: audit completed (orphans may or may not exist)
  1 - Warning: orphaned artifacts detected
  2 - Error: configuration or runtime error

See: ADR-035 Exit Code Standardization
Related: Issue #1379 (orphaned session artifacts)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

_SESSION_GLOB = ".agents/sessions/"
_MEMORY_GLOB = ".serena/memories/"


@dataclass
class BranchArtifacts:
    """Orphaned artifacts found on a single branch."""

    branch: str
    session_files: list[str] = field(default_factory=list)
    memory_files: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total artifact count on this branch."""
        return len(self.session_files) + len(self.memory_files)


@dataclass
class AuditReport:
    """Complete audit report across all branches."""

    timestamp: str
    base_ref: str
    branches_scanned: int = 0
    branches_with_orphans: int = 0
    total_session_files: int = 0
    total_memory_files: int = 0
    orphans: list[BranchArtifacts] = field(default_factory=list)

    @property
    def has_orphans(self) -> bool:
        """True when any orphaned artifacts were found."""
        return self.branches_with_orphans > 0


def _run_git(args: list[str]) -> str:
    """Run a git command and return stdout. Raises on failure."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = f"git {' '.join(args)} failed: {result.stderr.strip()}"
        raise RuntimeError(msg)
    return result.stdout.strip()


def list_remote_branches(exclude_patterns: list[str] | None = None) -> list[str]:
    """Return remote branch names (without origin/ prefix).

    Args:
        exclude_patterns: branch name prefixes to skip (e.g. ["renovate/"]).
    """
    if exclude_patterns is None:
        exclude_patterns = ["HEAD", "renovate/"]

    raw = _run_git(["branch", "-r", "--format=%(refname:short)"])
    branches = []
    for line in raw.splitlines():
        name = line.strip()
        if not name:
            continue
        short = name.removeprefix("origin/")
        if short == "main":
            continue
        if any(short.startswith(p) for p in exclude_patterns):
            continue
        branches.append(short)
    return sorted(branches)


def diff_files_vs_main(branch: str, base_ref: str = "origin/main") -> list[str]:
    """Return files that differ between a branch and base ref."""
    raw = _run_git(["diff", "--name-only", base_ref, f"origin/{branch}"])
    return [f for f in raw.splitlines() if f.strip()]


def find_orphaned_artifacts(
    branch: str,
    changed_files: list[str],
) -> BranchArtifacts:
    """Identify session and memory files not present on main."""
    artifacts = BranchArtifacts(branch=branch)
    for f in changed_files:
        if f.startswith(_SESSION_GLOB):
            artifacts.session_files.append(f)
        elif f.startswith(_MEMORY_GLOB):
            artifacts.memory_files.append(f)
    return artifacts


def audit_branches(
    base_ref: str = "origin/main",
    exclude_patterns: list[str] | None = None,
) -> AuditReport:
    """Scan all remote branches for orphaned session/memory artifacts.

    Args:
        base_ref: the ref to compare against (default origin/main).
        exclude_patterns: branch prefixes to skip.

    Returns:
        An AuditReport with all findings.
    """
    report = AuditReport(
        timestamp=datetime.now(UTC).isoformat(),
        base_ref=base_ref,
    )
    branches = list_remote_branches(exclude_patterns)
    report.branches_scanned = len(branches)

    for branch in branches:
        try:
            changed = diff_files_vs_main(branch, base_ref)
        except RuntimeError as exc:
            print(f"WARNING: skipping branch {branch}: {exc}", file=sys.stderr)
            continue

        artifacts = find_orphaned_artifacts(branch, changed)
        if artifacts.total > 0:
            report.orphans.append(artifacts)
            report.branches_with_orphans += 1
            report.total_session_files += len(artifacts.session_files)
            report.total_memory_files += len(artifacts.memory_files)

    return report


def format_report(report: AuditReport, output_format: str = "json") -> str:
    """Render the audit report as JSON or human-readable text."""
    if output_format == "json":
        return json.dumps(asdict(report), indent=2)

    lines = [
        f"Orphaned Branch Audit - {report.timestamp}",
        f"Base: {report.base_ref}",
        f"Branches scanned: {report.branches_scanned}",
        f"Branches with orphans: {report.branches_with_orphans}",
        f"Total session files: {report.total_session_files}",
        f"Total memory files: {report.total_memory_files}",
        "",
    ]
    if not report.has_orphans:
        lines.append("No orphaned artifacts found.")
    else:
        for orphan in report.orphans:
            lines.append(f"### {orphan.branch}")
            lines.append(f"  Sessions: {len(orphan.session_files)}")
            lines.append(f"  Memories: {len(orphan.memory_files)}")
            for sf in orphan.session_files:
                lines.append(f"    {sf}")
            for mf in orphan.memory_files:
                lines.append(f"    {mf}")
            lines.append("")

    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Audit remote branches for orphaned session/memory artifacts.",
    )
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Base ref to compare against (default: origin/main)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        dest="output_format",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=["HEAD", "renovate/"],
        help="Branch prefixes to exclude",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code per ADR-035."""
    args = parse_args(argv)

    try:
        report = audit_branches(
            base_ref=args.base_ref,
            exclude_patterns=args.exclude,
        )
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2

    print(format_report(report, args.output_format))
    return 1 if report.has_orphans else 0


if __name__ == "__main__":
    sys.exit(main())
