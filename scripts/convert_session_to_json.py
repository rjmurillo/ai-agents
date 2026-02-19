#!/usr/bin/env python3
"""Migrate markdown session logs to JSON format (wrapper for skill version).

Delegates to the session-migration skill for the actual conversion logic.
The skill version has additional features like work log parsing.

EXIT CODES:
  0  - Success: Session log(s) migrated successfully
  1  - Error: Skill script not found or migration failed

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def get_repo_root() -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate markdown session logs to JSON format"
    )
    parser.add_argument("path", help="Path to markdown session log file or directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing JSON files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated")
    args = parser.parse_args(argv)

    repo_root = get_repo_root()
    if not repo_root:
        print("ERROR: Not in a git repository", file=sys.stderr)
        return 1

    skill_script = (
        repo_root
        / ".claude"
        / "skills"
        / "session-migration"
        / "scripts"
        / "Convert-SessionToJson.ps1"
    )

    if not skill_script.exists():
        print(f"ERROR: Skill script not found: {skill_script}", file=sys.stderr)
        print(
            "This script delegates to the session-migration skill. "
            "Ensure the skill is present.",
            file=sys.stderr,
        )
        return 1

    skill_args = ["pwsh", "-NoProfile", "-File", str(skill_script), "-Path", args.path]
    if args.force:
        skill_args.append("-Force")
    if args.dry_run:
        skill_args.append("-DryRun")

    result = subprocess.run(skill_args)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
