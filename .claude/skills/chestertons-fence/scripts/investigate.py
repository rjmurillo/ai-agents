#!/usr/bin/env python3
"""Investigate historical context of existing code or patterns.

Performs git archaeology, PR/ADR search, and dependency analysis
to document why something exists before proposing changes.
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


def validate_path_no_traversal(path: Path, context: str = "path") -> Path:
    """Validate that path does not contain traversal patterns (CWE-22 protection)."""
    path_str = str(path)
    if ".." in path_str:
        raise PermissionError(
            f"Path traversal attempt detected: '{path}' contains prohibited '..' sequence."
        )

    resolved = path.resolve()

    if not path.is_absolute():
        try:
            resolved.relative_to(Path.cwd().resolve())
        except ValueError as e:
            raise PermissionError(
                f"Path traversal attempt detected: '{path}' resolves outside the working directory."
            ) from e

    return resolved


@dataclass
class InvestigationResult:
    """Result of a Chesterton's Fence investigation."""

    target: str
    proposed_change: str
    origin_commit: str = ""
    origin_date: str = ""
    origin_author: str = ""
    origin_message: str = ""
    related_prs: list[str] = field(default_factory=list)
    related_adrs: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_git(args: list[str]) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def find_origin_commit(target: str) -> tuple[str, str, str, str]:
    """Find when a file or pattern was first introduced.

    Returns:
        Tuple of (commit_hash, date, author, message)
    """
    path = Path(target)
    if path.exists():
        log_output = run_git([
            "log", "--diff-filter=A", "--follow",
            "--format=%H|%aI|%an|%s", "--", target,
        ])
        if log_output:
            lines = log_output.strip().split("\n")
            last_line = lines[-1]
            parts = last_line.split("|", 3)
            if len(parts) == 4:
                return parts[0], parts[1], parts[2], parts[3]

    return "", "", "", ""


def find_recent_changes(target: str, limit: int = 5) -> list[str]:
    """Find recent commits that modified the target."""
    log_output = run_git([
        "log", "-n", str(limit),
        "--format=%h %aI %s", "--", target,
    ])
    if log_output:
        return log_output.strip().split("\n")
    return []


def find_related_adrs(target: str) -> list[str]:
    """Search ADR files for references to the target."""
    adrs_dir = Path(".agents/architecture")
    if not adrs_dir.exists():
        return []

    target_name = Path(target).stem
    related = []
    for adr_file in sorted(adrs_dir.glob("ADR-*.md")):
        content = adr_file.read_text()
        if target_name in content or target in content:
            title_match = re.search(r"^# (.+)$", content, re.MULTILINE)
            title = title_match.group(1) if title_match else adr_file.name
            related.append(f"{adr_file.name}: {title}")

    return related


def find_dependents(target: str) -> list[str]:
    """Find files that reference the target."""
    target_path = Path(target)
    search_term = target_path.stem if target_path.exists() else target

    result = subprocess.run(
        ["git", "grep", "-l", search_term, "--", "*.md", "*.py", "*.ps1", "*.yml", "*.yaml"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode == 0 and result.stdout.strip():
        files = result.stdout.strip().split("\n")
        return [f for f in files if f != target]
    return []


def investigate(target: str, proposed_change: str) -> InvestigationResult:
    """Run a full Chesterton's Fence investigation."""
    result = InvestigationResult(target=target, proposed_change=proposed_change)

    commit, date, author, message = find_origin_commit(target)
    result.origin_commit = commit
    result.origin_date = date
    result.origin_author = author
    result.origin_message = message

    if not commit:
        result.warnings.append(
            f"Could not find origin commit for '{target}'. "
            "File may be untracked or the target may not be a file path."
        )

    result.related_adrs = find_related_adrs(target)
    result.dependents = find_dependents(target)

    if result.dependents:
        result.warnings.append(
            f"Found {len(result.dependents)} files referencing this target. "
            "Changes may have cascading effects."
        )

    return result


def generate_report(result: InvestigationResult) -> str:
    """Generate a markdown investigation report from results."""
    template_path = Path(".agents/templates/chestertons-fence-investigation.md")
    if not template_path.exists():
        return _generate_inline_report(result)

    report = template_path.read_text()
    report = report.replace("[Component/System Name]", result.target)

    return report + _generate_findings_appendix(result)


def _generate_inline_report(result: InvestigationResult) -> str:
    """Generate a report without using the template."""
    lines = [
        f"# Chesterton's Fence Investigation: {result.target}",
        "",
        "## Proposed Change",
        "",
        result.proposed_change,
        "",
        "## Git Archaeology",
        "",
    ]

    if result.origin_commit:
        lines.extend([
            f"- **Origin commit**: {result.origin_commit}",
            f"- **Date**: {result.origin_date}",
            f"- **Author**: {result.origin_author}",
            f"- **Message**: {result.origin_message}",
        ])
    else:
        lines.append("- No origin commit found.")

    lines.extend(["", "## Related ADRs", ""])
    if result.related_adrs:
        for adr in result.related_adrs:
            lines.append(f"- {adr}")
    else:
        lines.append("- None found.")

    lines.extend(["", "## Dependents", ""])
    if result.dependents:
        for dep in result.dependents:
            lines.append(f"- {dep}")
    else:
        lines.append("- None found.")

    if result.warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in result.warnings:
            lines.append(f"- {warning}")

    return "\n".join(lines) + "\n"


def _generate_findings_appendix(result: InvestigationResult) -> str:
    """Generate an appendix with automated findings."""
    lines = [
        "",
        "---",
        "",
        "## Automated Findings (investigate.py)",
        "",
        f"**Target**: {result.target}",
        f"**Proposed Change**: {result.proposed_change}",
        "",
        "### Git Archaeology",
        "",
    ]

    if result.origin_commit:
        lines.extend([
            f"- **Origin commit**: `{result.origin_commit[:12]}`",
            f"- **Date**: {result.origin_date}",
            f"- **Author**: {result.origin_author}",
            f"- **Message**: {result.origin_message}",
        ])
    else:
        lines.append("- No origin commit found.")

    lines.extend(["", "### Related ADRs", ""])
    if result.related_adrs:
        for adr in result.related_adrs:
            lines.append(f"- {adr}")
    else:
        lines.append("- None found.")

    lines.extend(["", "### Dependents", ""])
    if result.dependents:
        for dep in result.dependents:
            lines.append(f"- `{dep}`")
    else:
        lines.append("- None found.")

    if result.warnings:
        lines.extend(["", "### Warnings", ""])
        for warning in result.warnings:
            lines.append(f"- {warning}")

    return "\n".join(lines) + "\n"


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Investigate historical context before changing existing systems",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 investigate.py --target scripts/validate.py --change "remove unused validation"
  python3 investigate.py --target .agents/architecture/ADR-005.md --change "allow bash scripts"
  python3 investigate.py --target scripts/validate.py --change "refactor" --format json
        """,
    )

    parser.add_argument(
        "--target",
        required=True,
        help="File path, ADR number, or component to investigate",
    )
    parser.add_argument(
        "--change",
        required=True,
        help="Description of the proposed change",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    args = parser.parse_args()

    try:
        validate_path_no_traversal(Path(args.target), "target")
    except PermissionError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    result = investigate(args.target, args.change)

    if args.format == "json":
        output = {
            "target": result.target,
            "proposed_change": result.proposed_change,
            "origin": {
                "commit": result.origin_commit,
                "date": result.origin_date,
                "author": result.origin_author,
                "message": result.origin_message,
            },
            "related_adrs": result.related_adrs,
            "dependents": result.dependents,
            "warnings": result.warnings,
        }
        print(json.dumps(output, indent=2))
    else:
        report = generate_report(result)
        print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
