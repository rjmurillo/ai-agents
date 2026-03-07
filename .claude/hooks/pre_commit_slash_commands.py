#!/usr/bin/env python3
"""Pre-commit hook to validate staged slash command files.

Git pre-commit hook helper (called from .githooks/pre-commit), NOT a Claude Code hook.
Validates slash command frontmatter on staged .md files under .claude/commands/.

Uses standard POSIX exit codes (not Claude Hook Semantics):
    0 = All validations passed (or no files to validate)
    1 = One or more files failed validation
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Project root: this script lives at .claude/hooks/pre_commit_slash_commands.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]

VALIDATION_SCRIPT = (
    PROJECT_ROOT
    / ".claude"
    / "skills"
    / "slashcommandcreator"
    / "scripts"
    / "validate_slash_command.py"
)


def get_staged_slash_commands() -> list[str]:
    """Get staged .md files under .claude/commands/ from git."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return []

    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith(".claude/commands/") and line.strip().endswith(".md")
    ]


def validate_file(file_path: str) -> bool:
    """Run the validation script on a single file. Returns True if valid."""
    result = subprocess.run(
        [sys.executable, str(VALIDATION_SCRIPT), "--path", file_path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0


def main() -> int:
    """Main entry point. Returns exit code."""
    print("Validating staged slash commands...")

    staged_files = get_staged_slash_commands()

    if not staged_files:
        print("[SKIP] No slash command files staged, skipping validation")
        return 0

    print(f"Found {len(staged_files)} staged slash command(s)")

    failed_files: list[str] = []
    for file_path in staged_files:
        print(f"\nValidating: {file_path}")
        if not validate_file(file_path):
            failed_files.append(file_path)

    if failed_files:
        print(f"\n[FAIL] COMMIT BLOCKED: {len(failed_files)} file(s) failed validation")
        print("\nFailed files:")
        for f in failed_files:
            print(f"  - {f}")
        print("\nFix violations and try again.")
        print("Emergency bypass (if validation script has bugs): git commit --no-verify")
        return 1

    print("\n[PASS] All slash commands passed validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
