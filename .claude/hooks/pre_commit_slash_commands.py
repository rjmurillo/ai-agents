#!/usr/bin/env python3
"""Pre-commit hook to validate staged slash command files.

Checks staged .md files in .claude/commands/ and runs the validation
script on each. Blocks commit if any file fails validation.

Hook Type: Pre-commit (git hook)
Exit Codes:
    0 = All validations passed or no files to validate
    1 = One or more files failed validation
"""

import os
import subprocess
import sys


def get_staged_slash_commands() -> list[str]:
    """Return list of staged .md files under .claude/commands/."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith(".claude/commands/") and line.strip().endswith(".md")
    ]


def validate_file(validation_script: str, file_path: str) -> bool:
    """Run validation script on a single file. Return True if passed."""
    try:
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-File", validation_script, "-Path", file_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def main() -> None:
    """Entry point for the pre-commit slash commands hook."""
    print("Validating staged slash commands...")

    staged_files = get_staged_slash_commands()

    if not staged_files:
        print("[SKIP] No slash command files staged, skipping validation")
        sys.exit(0)

    print(f"Found {len(staged_files)} staged slash command(s)")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    validation_script = os.path.join(
        script_dir, "..", "skills", "slashcommandcreator", "scripts",
        "Validate-SlashCommand.ps1"
    )

    failed_files: list[str] = []

    for file_path in staged_files:
        print(f"\nValidating: {file_path}")
        if not validate_file(validation_script, file_path):
            failed_files.append(file_path)

    if failed_files:
        print(
            f"\n[FAIL] COMMIT BLOCKED: {len(failed_files)} file(s) failed validation"
        )
        print("\nFailed files:")
        for f in failed_files:
            print(f"  - {f}")
        print("\nFix violations and try again.")
        print(
            "Emergency bypass (if validation script has bugs): "
            "git commit --no-verify"
        )
        sys.exit(1)

    print("\n[PASS] All slash commands passed validation")
    sys.exit(0)


if __name__ == "__main__":
    main()
