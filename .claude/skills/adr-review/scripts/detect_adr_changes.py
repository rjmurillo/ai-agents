#!/usr/bin/env python3
"""Detect ADR file changes (create, update, delete) for automatic skill triggering.

Monitors ADR file patterns in designated directories and detects changes
since the last check. Returns structured JSON output for skill orchestration.

Patterns monitored:
- .agents/architecture/ADR-*.md
- docs/architecture/ADR-*.md

Exit codes follow ADR-035:
    0 - Success (changes detected or no changes found)
    1 - Logic or unexpected error during detection
    2 - Config/user error (invalid commit SHA, missing file)
    3 - External error (I/O failure, git command failure)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ADR_PATTERNS = (
    ".agents/architecture/ADR-*.md",
    "docs/architecture/ADR-*.md",
)

ADR_DIRECTORIES = (
    ".agents/architecture",
    "docs/architecture",
)


def _get_adr_status(file_path: Path) -> str:
    """Extract status from ADR frontmatter."""
    if not file_path.exists():
        return "unknown"
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    match = re.search(r"(?m)^status:\s*(.+)$", content)
    if match:
        return match.group(1).strip().lower()
    return "proposed"


def _get_dependent_adrs(adr_name: str, base_path: Path) -> list[str]:
    """Find ADRs that reference a given ADR."""
    dependents: list[str] = []
    for directory in ADR_DIRECTORIES:
        dir_path = base_path / directory
        if not dir_path.is_dir():
            continue
        for adr_file in dir_path.glob("ADR-*.md"):
            try:
                content = adr_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if adr_name in content:
                dependents.append(str(adr_file))
    return dependents


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect ADR file changes for automatic skill triggering.",
    )
    parser.add_argument(
        "--base-path",
        default=".",
        help="Repository root path (default: current directory)",
    )
    parser.add_argument(
        "--since-commit",
        default="HEAD~1",
        help="Git commit SHA to compare against (default: HEAD~1)",
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Include untracked new ADR files in detection",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_path = Path(args.base_path).resolve()

    if not (base_path / ".git").exists():
        print(f"Error: Not a git repository: {base_path}", file=sys.stderr)
        return 1

    (base_path / ".agents").mkdir(exist_ok=True)

    original_dir = os.getcwd()
    try:
        os.chdir(base_path)

        created: list[str] = []
        modified: list[str] = []
        deleted: list[str] = []

        for pattern in ADR_PATTERNS:
            result = _run_git(
                ["diff", "--name-status", args.since_commit, "--", pattern],
                cwd=base_path,
            )
            if result.returncode != 0:
                print(
                    f"Error: git diff failed for pattern '{pattern}': {result.stderr.strip()}",
                    file=sys.stderr,
                )
                return 3

            for line in result.stdout.strip().splitlines():
                match = re.match(r"^([AMD])\s+(.+)$", line)
                if match:
                    status_char = match.group(1)
                    file_path = match.group(2)
                    if status_char == "A":
                        created.append(file_path)
                    elif status_char == "M":
                        modified.append(file_path)
                    elif status_char == "D":
                        deleted.append(file_path)

        if args.include_untracked:
            for directory in ADR_DIRECTORIES:
                dir_path = base_path / directory
                if not dir_path.is_dir():
                    continue
                result = _run_git(
                    ["ls-files", "--others", "--exclude-standard", "--", f"{directory}/ADR-*.md"],
                    cwd=base_path,
                )
                if result.returncode != 0:
                    print(
                        f"Warning: git ls-files failed for '{directory}': {result.stderr.strip()}",
                        file=sys.stderr,
                    )
                    continue
                for line in result.stdout.strip().splitlines():
                    if line:
                        created.append(line)

        created = sorted(set(created))
        modified = sorted(set(modified))
        deleted = sorted(set(deleted))

        recommended_action = "none"
        if created:
            recommended_action = "review"
        elif modified:
            recommended_action = "review"
        elif deleted:
            recommended_action = "archive"

        deleted_details = []
        for file_path in deleted:
            adr_name = Path(file_path).stem
            dependents = _get_dependent_adrs(adr_name, base_path)
            deleted_details.append({
                "Path": file_path,
                "ADRName": adr_name,
                "Status": "deleted",
                "Dependents": dependents,
            })

        result_obj = {
            "Created": created,
            "Modified": modified,
            "Deleted": deleted,
            "DeletedDetails": deleted_details,
            "HasChanges": len(created) + len(modified) + len(deleted) > 0,
            "RecommendedAction": recommended_action,
            "Timestamp": datetime.now(UTC).isoformat(),
            "SinceCommit": args.since_commit,
        }

        print(json.dumps(result_obj, indent=2))
        return 0

    except FileNotFoundError as exc:
        print(f"Error: File or directory not found: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Error: I/O failure: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Error detecting ADR changes: {exc}", file=sys.stderr)
        return 1
    finally:
        os.chdir(original_dir)


if __name__ == "__main__":
    raise SystemExit(main())
