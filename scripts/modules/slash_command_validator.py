"""Module for slash command validation (ADR-006: logic in modules, not workflows)."""

from __future__ import annotations

import sys
from pathlib import Path

# Add the validation script's directory to the import path
_VALIDATOR_DIR = str(
    Path(__file__).resolve().parent.parent.parent
    / ".claude"
    / "skills"
    / "slashcommandcreator"
    / "scripts"
)


def invoke_slash_command_validation() -> int:
    """Validate all slash command files in .claude/commands/.

    Runs validation on each .md file in .claude/commands/.
    Skips catalog files (README.md, index files, CLAUDE.md) that do not require
    frontmatter.

    Returns:
        0 if all pass, 1 if any fail.
    """
    commands_dir = Path(".claude/commands")
    if not commands_dir.exists():
        print("No slash command files found, skipping validation")
        return 0

    catalog_files = {"README.md", "INDEX.md", "CATALOG.md", "CLAUDE.md"}

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

    # Import the Python validator (migrated from Validate-SlashCommand.ps1)
    if _VALIDATOR_DIR not in sys.path:
        sys.path.insert(0, _VALIDATOR_DIR)

    from validate_slash_command import validate_slash_command

    failed_files: list[str] = []

    for file_path in command_files:
        print(f"\nValidating: {file_path}")
        # Skip lint here; markdownlint runs separately in CI with proper config.
        # The per-file lint in validate_slash_command picks up the global
        # .markdownlint-cli2.jsonc globs and lints all 233 files, not just
        # the target file.
        violations, blocking_count, _warning_count = validate_slash_command(
            str(file_path), skip_lint=True,
        )
        if blocking_count > 0:
            for v in violations:
                print(f"  {v}")
            failed_files.append(file_path.name)

    if failed_files:
        print(f"\n[FAIL] VALIDATION FAILED: {len(failed_files)} file(s) failed")
        print("\nFailed files:")
        for name in failed_files:
            print(f"  - {name}")
        return 1

    print("\n[PASS] All slash commands passed quality gates")
    return 0
