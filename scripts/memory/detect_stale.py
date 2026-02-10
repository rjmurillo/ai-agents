#!/usr/bin/env python3
"""
Detect stale, obsolete, or orphaned Serena memory files.

Checks:
- Last git modification date (flags >6 months unmodified)
- Cross-references to codebase files (do referenced paths still exist?)
- Broken internal links (do referenced memories still exist?)

Non-destructive: generates report only, never deletes files.

Exit codes per ADR-035:
  0 - Success (report generated)
  1 - Error (git not available, path not found)
"""

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class StaleReport:
    """Report for a single memory file."""

    file_path: str
    last_modified: datetime | None = None
    days_since_modified: int = 0
    is_stale: bool = False
    broken_links: list[str] = field(default_factory=list)
    broken_code_refs: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


STALE_DAYS = 180  # 6 months

# Pattern for markdown links to .md files
MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")

# Pattern for code file references (backtick-wrapped paths)
CODE_REF = re.compile(
    r"`([a-zA-Z0-9_./-]+\.(py|ps1|psm1|yml|yaml|json|ts|js|sh))`"
)


def get_git_last_modified(file_path: Path) -> datetime | None:
    """Get last git modification date for a file."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            msg = f"git log failed for {file_path}: {result.stderr.strip()}"
            print(f"Warning: {msg}", file=sys.stderr)
            return None
        if result.stdout.strip():
            return datetime.fromisoformat(result.stdout.strip())
    except ValueError as e:
        print(f"Warning: invalid git date for {file_path}: {e}", file=sys.stderr)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def find_broken_links(
    content: str, memories_dir: Path
) -> list[str]:
    """Find markdown links to non-existent memory files."""
    broken = []
    for match in MD_LINK.finditer(content):
        target = match.group(2)
        # Skip external URLs and anchors
        if target.startswith(("http", "#", "/")):
            continue
        target_path = memories_dir / target
        if not target_path.exists():
            broken.append(target)
    return broken


def find_broken_code_refs(
    content: str, repo_root: Path
) -> list[str]:
    """Find references to code files that no longer exist."""
    broken = []
    for match in CODE_REF.finditer(content):
        ref_path = match.group(1)
        # Skip common non-path patterns
        if ref_path.startswith(("$", "{", "<", "/")):
            continue
        # Skip template placeholders (YYYY, NN patterns)
        if "YYYY" in ref_path or "-NN" in ref_path:
            continue
        # Skip bare file extensions used as type references
        if ref_path.startswith(".") and "/" not in ref_path:
            continue
        # Only check paths that look like they reference repo files
        if "/" in ref_path or ref_path.startswith("."):
            full_path = repo_root / ref_path
            if not full_path.exists():
                broken.append(ref_path)
    return broken


def analyze_file(
    file_path: Path,
    memories_dir: Path,
    repo_root: Path,
    stale_days: int = STALE_DAYS,
    stale_only: bool = False,
) -> StaleReport:
    """Analyze a single memory file for staleness."""
    report = StaleReport(file_path=str(file_path.relative_to(repo_root)))

    # Check git modification date
    last_mod = get_git_last_modified(file_path)
    if last_mod:
        report.last_modified = last_mod
        now = datetime.now(UTC)
        report.days_since_modified = (now - last_mod).days
        report.is_stale = report.days_since_modified > stale_days

    # Read content and check links (skip if stale_only)
    content = file_path.read_text(encoding="utf-8")
    if not stale_only:
        report.broken_links = find_broken_links(content, memories_dir)
        report.broken_code_refs = find_broken_code_refs(content, repo_root)

    # Generate recommendations
    if report.is_stale:
        report.recommendations.append(
            f"Stale: not modified in {report.days_since_modified} days. "
            f"Review for archival or update."
        )
    if report.broken_links:
        report.recommendations.append(
            f"Has {len(report.broken_links)} broken memory link(s). "
            f"Update or remove references."
        )
    if report.broken_code_refs:
        report.recommendations.append(
            f"Has {len(report.broken_code_refs)} broken code reference(s). "
            f"Referenced files may have been moved or deleted."
        )

    return report


def format_report(reports: list[StaleReport]) -> str:
    """Format analysis results as a readable report."""
    lines = ["# Memory Staleness Report", ""]
    now = datetime.now(UTC)
    lines.append(f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Total files analyzed: {len(reports)}")
    lines.append("")

    stale = [r for r in reports if r.is_stale]
    broken_links = [r for r in reports if r.broken_links]
    broken_refs = [r for r in reports if r.broken_code_refs]
    clean = [
        r
        for r in reports
        if not r.is_stale and not r.broken_links and not r.broken_code_refs
    ]

    lines.append("## Summary")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| Stale (>{STALE_DAYS} days) | {len(stale)} |")
    lines.append(f"| Broken memory links | {len(broken_links)} |")
    lines.append(f"| Broken code references | {len(broken_refs)} |")
    lines.append(f"| Clean | {len(clean)} |")
    lines.append("")

    if stale:
        lines.append("## Stale Memories")
        lines.append("")
        for r in sorted(stale, key=lambda x: x.days_since_modified, reverse=True):
            mod_date = r.last_modified.strftime("%Y-%m-%d") if r.last_modified else "unknown"
            lines.append(f"- **{r.file_path}** ({r.days_since_modified} days, last: {mod_date})")
        lines.append("")

    if broken_links:
        lines.append("## Broken Memory Links")
        lines.append("")
        for r in broken_links:
            lines.append(f"- **{r.file_path}**:")
            for link in r.broken_links:
                lines.append(f"  - `{link}`")
        lines.append("")

    if broken_refs:
        lines.append("## Broken Code References")
        lines.append("")
        for r in broken_refs:
            lines.append(f"- **{r.file_path}**:")
            for ref in r.broken_code_refs:
                lines.append(f"  - `{ref}`")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect stale, obsolete, or orphaned Serena memory files"
    )
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        help="Memory directory (default: auto-detect from repo root)",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=STALE_DAYS,
        help=f"Days before a memory is considered stale (default: {STALE_DAYS})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write report to file instead of stdout",
    )
    parser.add_argument(
        "--stale-only",
        action="store_true",
        help="Only report stale files (skip link checks)",
    )
    args = parser.parse_args()

    # Determine paths
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            print("Error: not in a git repository", file=sys.stderr)
            return 1
        repo_root = Path(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("Error: git not available", file=sys.stderr)
        return 1

    memories_dir = (args.path or (repo_root / ".serena" / "memories")).resolve()
    if not memories_dir.exists():
        print(f"Error: {memories_dir} not found", file=sys.stderr)
        return 1

    # Analyze all memory files
    reports = []
    skipped = 0
    for md_file in sorted(memories_dir.glob("*.md")):
        if md_file.name == "README.md":
            continue
        try:
            report = analyze_file(
                md_file, memories_dir, repo_root,
                args.stale_days, args.stale_only,
            )
            reports.append(report)
        except (OSError, UnicodeDecodeError) as e:
            print(f"Warning: Failed to analyze {md_file.name}: {e}", file=sys.stderr)
            skipped += 1

    if skipped:
        print(f"Warning: {skipped} file(s) skipped due to errors", file=sys.stderr)

    if not reports:
        print("No memory files found", file=sys.stderr)
        return 1

    # Format and output
    output = format_report(reports)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
