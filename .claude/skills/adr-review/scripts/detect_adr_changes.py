#!/usr/bin/env python3
"""Detect ADR file changes (create, update, delete) for automatic skill triggering.

Monitors ADR file patterns in designated directories and detects changes
since the last check. Returns structured JSON output for skill orchestration.

Patterns monitored:
- .agents/architecture/ADR-*.md
- docs/architecture/ADR-*.md

EXIT CODES (ADR-035):
    0 - Success: Changes detected or no changes found
    1 - Error: Logic or unexpected error
    2 - Error: Config/user error (invalid commit SHA, missing file)
    3 - Error: External error (I/O failure, git command failure)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ADR_PATTERNS = [
    ".agents/architecture/ADR-*.md",
    "docs/architecture/ADR-*.md",
]

ADR_DIRECTORIES = [
    ".agents/architecture",
    "docs/architecture",
]


def get_adr_status(file_path: str) -> str:
    """Extract status from ADR frontmatter."""
    path = Path(file_path)
    if not path.exists():
        return "unknown"
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    match = re.search(r"^status:\s*(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip().lower()
    return "proposed"


def get_dependent_adrs(adr_name: str, base_path: str) -> list[str]:
    """Find ADRs that reference a given ADR."""
    dependents: list[str] = []
    for directory in ADR_DIRECTORIES:
        dir_path = Path(base_path) / directory
        if not dir_path.exists():
            continue
        for adr_file in dir_path.glob("ADR-*.md"):
            try:
                content = adr_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if adr_name in content:
                dependents.append(str(adr_file))
    return dependents


def run_git(args: list[str], cwd: str) -> tuple[int, str]:
    """Run a git command and return (returncode, stdout)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )
        return result.returncode, result.stdout.strip()
    except FileNotFoundError:
        return -1, "git not found"
    except subprocess.TimeoutExpired:
        return -1, "git command timed out"


def detect_adr_changes(
    base_path: str = ".",
    since_commit: str = "HEAD~1",
    include_untracked: bool = False,
) -> dict:
    """Detect ADR file changes and return structured result."""
    base = Path(base_path).resolve()

    if not (base / ".git").exists():
        print(f"Error: Not a git repository: {base}", file=sys.stderr)
        sys.exit(2)

    created: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []

    for pattern in ADR_PATTERNS:
        returncode, output = run_git(
            ["diff", "--name-status", since_commit, "--", pattern],
            cwd=str(base),
        )
        if returncode != 0:
            if "git not found" in output:
                print(f"Error: External dependency not found (git): {output}", file=sys.stderr)
                sys.exit(3)
            print(
                f"Error: git diff failed for pattern '{pattern}': {output}",
                file=sys.stderr,
            )
            sys.exit(3)

        if output:
            for line in output.splitlines():
                match = re.match(r"^([AMD])\s+(.+)$", line)
                if match:
                    status = match.group(1)
                    file_path = match.group(2)
                    if status == "A":
                        created.append(file_path)
                    elif status == "M":
                        modified.append(file_path)
                    elif status == "D":
                        deleted.append(file_path)

    if include_untracked:
        for directory in ADR_DIRECTORIES:
            dir_path = base / directory
            if not dir_path.exists():
                continue
            returncode, output = run_git(
                ["ls-files", "--others", "--exclude-standard", "--", f"{directory}/ADR-*.md"],
                cwd=str(base),
            )
            if returncode != 0:
                print(
                    f"Warning: git ls-files failed for directory '{directory}': {output}",
                    file=sys.stderr,
                )
                continue
            if output:
                for line in output.splitlines():
                    if line.strip():
                        created.append(line.strip())

    created = sorted(set(filter(None, created)))
    modified = sorted(set(filter(None, modified)))
    deleted = sorted(set(filter(None, deleted)))

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
        dependents = get_dependent_adrs(adr_name, str(base))
        deleted_details.append({
            "Path": file_path,
            "ADRName": adr_name,
            "Status": "deleted",
            "Dependents": dependents,
        })

    result = {
        "Created": created,
        "Modified": modified,
        "Deleted": deleted,
        "DeletedDetails": deleted_details,
        "HasChanges": len(created) + len(modified) + len(deleted) > 0,
        "RecommendedAction": recommended_action,
        "Timestamp": datetime.now(timezone.utc).isoformat(),
        "SinceCommit": since_commit,
    }

    return result


def main() -> int:
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Detect ADR file changes")
    parser.add_argument("--base-path", default=".", help="Repository root path")
    parser.add_argument("--since-commit", default="HEAD~1", help="Git commit SHA to compare against")
    parser.add_argument("--include-untracked", action="store_true", help="Include untracked new ADR files")
    args = parser.parse_args()

    try:
        result = detect_adr_changes(
            base_path=args.base_path,
            since_commit=args.since_commit,
            include_untracked=args.include_untracked,
        )
        print(json.dumps(result, indent=2))
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except FileNotFoundError as e:
        print(f"Error: File or directory not found: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Error: I/O failure: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"Error detecting ADR changes: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
