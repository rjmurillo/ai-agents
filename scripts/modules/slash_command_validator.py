"""Module for slash command validation (ADR-006: logic in modules, not workflows)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def invoke_slash_command_validation() -> int:
    """Validate all slash command files in .claude/commands/.

    Runs validation on each .md file in .claude/commands/.
    Skips catalog files (README.md, index files) that do not require frontmatter.

    Returns:
        0 if all pass, 1 if any fail.
    """
    commands_dir = Path(".claude/commands")
    if not commands_dir.exists():
        print("No slash command files found, skipping validation")
        return 0

    catalog_files = {"README.md", "INDEX.md", "CATALOG.md"}

    command_files = [
        f
        for f in commands_dir.rglob("*.md")
        if f.name not in catalog_files
    ]

    if not command_files:
        print(
            "No slash command files found (only catalog files), skipping validation"
        )
        return 0

    print(
        f"Found {len(command_files)} slash command file(s) to validate "
        f"(excluding catalog files)"
    )

    validation_script = ".claude/skills/slashcommandcreator/scripts/Validate-SlashCommand.ps1"
    failed_files: list[str] = []

    for file_path in command_files:
        print(f"\nValidating: {file_path}")
        result = subprocess.run(
            ["pwsh", "-NoProfile", "-File", validation_script, "-Path", str(file_path)],
            capture_output=False,
        )
        if result.returncode != 0:
            failed_files.append(file_path.name)

    if failed_files:
        print(f"\n[FAIL] VALIDATION FAILED: {len(failed_files)} file(s) failed")
        print("\nFailed files:")
        for name in failed_files:
            print(f"  - {name}")
        return 1

    print("\n[PASS] All slash commands passed quality gates")
    return 0
