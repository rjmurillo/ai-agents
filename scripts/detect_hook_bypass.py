#!/usr/bin/env python3
"""Detect commits that bypassed pre-commit hooks via --no-verify.

Analyzes PR commits to identify those that likely bypassed the pre-commit hook.
Detection heuristics:
  - Commits modifying .agents/ files without a session log in the same commit
  - Commits modifying HANDOFF.md on feature branches
  - Commits with markdown lint violations that auto-fix would have caught

Results are logged as structured JSON for metrics and audit trail.

EXIT CODES:
  0 - Success: No bypass indicators detected
  1 - Warning: Bypass indicators found (non-blocking, logged for audit)
  2 - Error: Configuration or runtime error

See: ADR-035 Exit Code Standardization
Related: Issue #664 (--no-verify bypass logging)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Matches squashed merge-resolution commits (single parent, merge-like subject)
_MERGE_SUBJECT_RE = re.compile(
    r"^Merge (branch|remote-tracking branch) '.+' into .+"
)


@dataclass
class BypassIndicator:
    """A single indicator that a commit may have bypassed pre-commit hooks."""

    commit_sha: str
    commit_message: str
    indicator_type: str
    details: str


@dataclass
class AuditReport:
    """Structured audit report of bypass detection results."""

    timestamp: str
    branch: str
    base_ref: str
    total_commits: int
    bypass_indicators: list[BypassIndicator] = field(default_factory=list)

    @property
    def has_indicators(self) -> bool:
        """Return True when bypass indicators exist."""
        return len(self.bypass_indicators) > 0


def get_current_branch() -> str:
    """Get the current git branch name."""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def get_pr_commits(base_ref: str) -> list[tuple[str, str]]:
    """Get non-merge commits in the PR (since diverging from base).

    Skips merge commits because they integrate changes already validated
    on their source branches. Also skips squashed merge-resolution commits
    (single-parent commits with merge-like subjects) since they only
    bring in base-branch changes. Only authored commits are checked for
    hook bypass indicators.

    Returns list of (sha, subject) tuples.
    """
    result = subprocess.run(
        [
            "git",
            "log",
            "--no-merges",
            f"{base_ref}..HEAD",
            "--format=%H %s",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        return []
    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        sha, _, subject = line.partition(" ")
        if _MERGE_SUBJECT_RE.match(subject):
            continue
        commits.append((sha, subject))
    return commits


def get_commit_files(sha: str) -> list[str]:
    """Get files changed in a specific commit."""
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "-r", "-m", "--name-only", sha],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


def check_agents_without_session(
    sha: str,
    subject: str,
    files: list[str],
) -> BypassIndicator | None:
    """Check if commit modifies .agents/ files without a session log."""
    has_agents_files = any(f.startswith(".agents/") for f in files)
    has_session_log = any(
        f.startswith(".agents/sessions/") and f.endswith(".json") for f in files
    )
    if has_agents_files and not has_session_log:
        return BypassIndicator(
            commit_sha=sha,
            commit_message=subject,
            indicator_type="agents-without-session",
            details="Commit modifies .agents/ files without a session log",
        )
    return None


def check_handoff_modified(
    sha: str,
    subject: str,
    files: list[str],
) -> BypassIndicator | None:
    """Check if commit modifies HANDOFF.md (blocked by pre-commit hook)."""
    if ".agents/HANDOFF.md" in files:
        return BypassIndicator(
            commit_sha=sha,
            commit_message=subject,
            indicator_type="handoff-modified",
            details="HANDOFF.md modified on feature branch (blocked by pre-commit hook)",
        )
    return None


def check_bash_scripts_added(
    sha: str,
    subject: str,
    files: list[str],
) -> BypassIndicator | None:
    """Check if commit adds bash scripts under .github/scripts/ (blocked by hook)."""
    bash_files = [
        f
        for f in files
        if f.startswith(".github/scripts/") and f.endswith((".sh", ".bash"))
    ]
    if bash_files:
        return BypassIndicator(
            commit_sha=sha,
            commit_message=subject,
            indicator_type="bash-script-added",
            details=(
                "Bash script(s) under .github/scripts/ (ADR-042 violation): "
                f"{', '.join(bash_files)}"
            ),
        )
    return None


def analyze_commits(
    base_ref: str,
) -> AuditReport:
    """Analyze PR commits for bypass indicators."""
    branch = get_current_branch()
    commits = get_pr_commits(base_ref)

    report = AuditReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        branch=branch,
        base_ref=base_ref,
        total_commits=len(commits),
    )

    checks = [
        check_agents_without_session,
        check_handoff_modified,
        check_bash_scripts_added,
    ]

    for sha, subject in commits:
        files = get_commit_files(sha)
        for check_fn in checks:
            indicator = check_fn(sha, subject, files)
            if indicator is not None:
                report.bypass_indicators.append(indicator)

    return report


def format_report(report: AuditReport) -> str:
    """Format audit report as human-readable text."""
    lines = [
        "Hook Bypass Audit Report",
        f"Branch: {report.branch}",
        f"Base: {report.base_ref}",
        f"Commits analyzed: {report.total_commits}",
        f"Bypass indicators: {len(report.bypass_indicators)}",
        "",
    ]

    if not report.has_indicators:
        lines.append("No bypass indicators detected.")
        return "\n".join(lines)

    for indicator in report.bypass_indicators:
        short_sha = indicator.commit_sha[:8]
        lines.append(
            f"  [{short_sha}] {indicator.indicator_type}: {indicator.details}"
        )
        lines.append(f"           Message: {indicator.commit_message}")
        lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-ref",
        default="origin/main",
        help="Base reference for comparison (default: origin/main)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write JSON report to file (implies --json)",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point. Returns exit code per ADR-035."""
    try:
        args = parse_args()

        report = analyze_commits(args.base_ref)

        if args.output or args.json_output:
            report_dict = asdict(report)
            json_str = json.dumps(report_dict, indent=2)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json_str + "\n", encoding="utf-8")
                print(f"Report written to {args.output}")
            else:
                print(json_str)
        else:
            print(format_report(report))

        if report.has_indicators:
            return 1

        return 0

    except subprocess.TimeoutExpired:
        print("ERROR: Git command timed out", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
