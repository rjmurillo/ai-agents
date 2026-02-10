#!/usr/bin/env python3
"""Validate that all GitHub Actions are pinned to commit SHA, not version tags.

Scans all workflow files in .github/workflows/ and .github/actions/ for
third-party action references. Ensures actions are pinned to commit SHA
(40 hex characters) rather than mutable version tags (e.g., @v4, @v3.2.1).

Implements security constraint from PROJECT-CONSTRAINTS.md.

Exit codes follow ADR-035:
    0 - Success (all actions SHA-pinned, or no violations in non-CI mode)
    1 - Logic error (violations found, CI mode only)
    2 - Config error (path not found)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Regex to detect version tag usage per SEMVER 2.0.0
# Matches: uses: <action>@v<major>[.<minor>][.<patch>][-<prerelease>][+<buildmetadata>]
# The version tag pattern starts with 'v' followed by digits.
# Prerelease: hyphen followed by dot-separated alphanumeric identifiers
# Build metadata: plus followed by dot-separated alphanumeric identifiers
VERSION_TAG_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*-?\s*uses:\s+([^@]+)@"
    r"(v\d+(?:\.\d+)*"
    r"(?:-[a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*)?"
    r"(?:\+[a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*)?)"
    r"\s*(?:#.*)?$"
)

# Pattern to skip local actions (uses: ./)
LOCAL_ACTION_PATTERN: re.Pattern[str] = re.compile(r"^\s*uses:\s+\./")

# ANSI color codes
_COLOR_RESET = "\033[0m"
_COLOR_RED = "\033[31m"
_COLOR_YELLOW = "\033[33m"
_COLOR_GREEN = "\033[32m"
_COLOR_CYAN = "\033[36m"


@dataclass
class Violation:
    """A SHA pinning violation found in a workflow file."""

    file: str
    full_path: str
    line: int
    action: str
    tag: str
    content: str


def find_workflow_files(base_path: Path) -> list[Path]:
    """Find all YAML workflow and action files under the given path."""
    workflow_dir = base_path / ".github" / "workflows"
    actions_dir = base_path / ".github" / "actions"

    files: list[Path] = []

    if workflow_dir.is_dir():
        files.extend(workflow_dir.glob("*.yml"))
        files.extend(workflow_dir.glob("*.yaml"))

    if actions_dir.is_dir():
        files.extend(actions_dir.rglob("*.yml"))
        files.extend(actions_dir.rglob("*.yaml"))

    return sorted(files)


def scan_file(file_path: Path) -> list[Violation]:
    """Scan a single file for version tag violations."""
    violations: list[Violation] = []
    lines = file_path.read_text(encoding="utf-8").splitlines()

    for line_num, line in enumerate(lines, start=1):
        if LOCAL_ACTION_PATTERN.search(line):
            continue

        match = VERSION_TAG_PATTERN.match(line)
        if match:
            violations.append(
                Violation(
                    file=file_path.name,
                    full_path=str(file_path),
                    line=line_num,
                    action=match.group(1),
                    tag=match.group(2),
                    content=line.strip(),
                )
            )

    return violations


def scan_all(base_path: Path) -> tuple[list[Path], list[Violation]]:
    """Scan all workflow files for violations.

    Returns (files_scanned, violations).
    """
    files = find_workflow_files(base_path)
    all_violations: list[Violation] = []
    for f in files:
        all_violations.extend(scan_file(f))
    return files, all_violations


def format_console(
    files: list[Path], violations: list[Violation]
) -> tuple[str, int]:
    """Format results for console output. Returns (output, exit_code_modifier).

    exit_code_modifier: 0 if pass, 1 if violations found.
    """
    lines: list[str] = []

    if not violations:
        lines.append(
            f"{_COLOR_GREEN}All GitHub Actions are SHA-pinned{_COLOR_RESET}"
        )
        lines.append(
            f"{_COLOR_CYAN}   Scanned {len(files)} workflow file(s){_COLOR_RESET}"
        )
        return "\n".join(lines), 0

    lines.append(
        f"{_COLOR_RED}GitHub Actions MUST be pinned to SHA, "
        f"not version tags{_COLOR_RESET}"
    )
    lines.append("")
    lines.append(
        f"{_COLOR_YELLOW}Found {len(violations)} violation(s):{_COLOR_RESET}"
    )
    lines.append("")

    for v in violations:
        lines.append(f"  {_COLOR_RED}{v.file}:{v.line}{_COLOR_RESET}")
        lines.append(
            f"    {_COLOR_YELLOW}uses: {v.action}@{v.tag}{_COLOR_RESET}"
        )

    lines.append("")
    lines.append(f"{_COLOR_CYAN}Required pattern:{_COLOR_RESET}")
    lines.append(
        f"  {_COLOR_GREEN}uses: actions/checkout@"
        f"11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2{_COLOR_RESET}"
    )
    lines.append("")
    lines.append(f"{_COLOR_CYAN}To find SHA for a version tag:{_COLOR_RESET}")
    lines.append(
        f"  {_COLOR_CYAN}gh api repos/<owner>/<repo>/git/ref/tags/<tag>"
        f" --jq '.object.sha'{_COLOR_RESET}"
    )

    return "\n".join(lines), 1


def format_markdown(
    files: list[Path], violations: list[Violation]
) -> tuple[str, int]:
    """Format results as markdown. Returns (output, exit_code_modifier)."""
    lines: list[str] = []
    lines.append("## GitHub Actions SHA Pinning Validation")
    lines.append("")

    if not violations:
        lines.append("**Status**: PASS")
        lines.append("")
        lines.append(f"**Files Scanned**: {len(files)}")
        lines.append("")
        lines.append("All GitHub Actions are properly pinned to commit SHA.")
        return "\n".join(lines), 0

    lines.append("**Status**: FAIL")
    lines.append("")
    lines.append(f"**Files Scanned**: {len(files)}")
    lines.append("")
    lines.append(f"**Violations Found**: {len(violations)}")
    lines.append("")
    lines.append("### Violations")
    lines.append("")
    lines.append("| File | Line | Action | Tag |")
    lines.append("|------|------|--------|-----|")

    for v in violations:
        lines.append(f"| {v.file} | {v.line} | `{v.action}` | `{v.tag}` |")

    lines.append("")
    lines.append("### Required Pattern")
    lines.append("")
    lines.append("```yaml")
    lines.append(
        "uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2"
    )
    lines.append("```")
    lines.append("")
    lines.append("### How to Fix")
    lines.append("")
    lines.append("Find SHA for version tag:")
    lines.append("```bash")
    lines.append(
        "gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.sha'"
    )
    lines.append("```")

    return "\n".join(lines), 1


def format_json(
    files: list[Path], violations: list[Violation]
) -> tuple[str, int]:
    """Format results as JSON. Returns (output, exit_code_modifier)."""
    if not violations:
        data = {
            "status": "pass",
            "filesScanned": len(files),
            "violations": [],
        }
        return json.dumps(data, indent=2), 0

    data = {
        "status": "fail",
        "filesScanned": len(files),
        "violationCount": len(violations),
        "violations": [
            {
                "file": v.file,
                "line": v.line,
                "action": v.action,
                "tag": v.tag,
                "content": v.content,
            }
            for v in violations
        ],
    }
    return json.dumps(data, indent=2), 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_FORMATTERS = {
    "console": format_console,
    "markdown": format_markdown,
    "json": format_json,
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description="Validate GitHub Actions are pinned to commit SHA.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("SCAN_PATH", "."),
        help="Base path to scan (env: SCAN_PATH, default: current directory)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit non-zero on violations (env: CI)",
    )
    parser.add_argument(
        "--format",
        choices=("console", "markdown", "json"),
        default=os.environ.get("OUTPUT_FORMAT", "console"),
        dest="output_format",
        help="Output format (env: OUTPUT_FORMAT, default: console)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    base_path = Path(args.path).resolve()
    if not base_path.is_dir():
        print(f"Error: Path not found: {args.path}", file=sys.stderr)
        return 2  # ADR-035: config error (path not found)

    files, violations = scan_all(base_path)

    if not files:
        if args.output_format == "console":
            print(
                f"No .github/workflows or .github/actions directories "
                f"found at {base_path}"
            )
        elif args.output_format == "json":
            print(
                json.dumps(
                    {
                        "status": "skipped",
                        "message": "No workflow or action files found",
                        "violations": [],
                    },
                    indent=2,
                )
            )
        return 0

    formatter = _FORMATTERS[args.output_format]
    output, has_violations = formatter(files, violations)
    print(output)

    if has_violations and args.ci:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
