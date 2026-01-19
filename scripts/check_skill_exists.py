#!/usr/bin/env python3
"""Check if a skill script exists for the specified operation and action.

Self-documenting tool that discovers skills via file system scan.
Used by Phase 1.5 BLOCKING gate to verify skill availability before operations.

This is a Python port of Check-SkillExists.ps1 following ADR-042 migration.

EXIT CODES:
  0  - Success: Skill found or list completed
  1  - Error: Skill not found or invalid parameters
  2  - Error: Unexpected error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utils.path_validation import validate_safe_path  # noqa: E402

# Valid operations for skill lookup
VALID_OPERATIONS = frozenset({"pr", "issue", "reactions", "label", "milestone"})


def get_skill_base_path(project_root: Path) -> Path:
    """Get the base path for skill scripts.

    Args:
        project_root: The project root directory.

    Returns:
        Path to the skill scripts directory.
    """
    return project_root / ".claude" / "skills" / "github" / "scripts"


def list_available_skills(skill_base_path: Path) -> None:
    """List all available skills organized by operation type.

    Args:
        skill_base_path: Base path to skill scripts directory.
    """
    for operation in sorted(VALID_OPERATIONS):
        operation_path = skill_base_path / operation
        if operation_path.exists() and operation_path.is_dir():
            print(f"\n=== {operation} ===")
            for script in sorted(operation_path.glob("*.ps1")):
                print(f"  - {script.stem}")


def check_skill_exists(
    skill_base_path: Path,
    operation: str,
    action: str,
) -> bool:
    """Check if a skill script exists for the given operation and action.

    Args:
        skill_base_path: Base path to skill scripts directory.
        operation: The operation type (pr, issue, reactions, label, milestone).
        action: The action name to check for (uses substring matching).

    Returns:
        True if a matching skill script exists, False otherwise.

    Raises:
        ValueError: If action is empty (required for meaningful search).
    """
    if not action:
        raise ValueError("Action cannot be empty")

    if operation not in VALID_OPERATIONS:
        print(f"ERROR: Invalid operation: {operation}", file=sys.stderr)
        print(f"Valid operations: {', '.join(sorted(VALID_OPERATIONS))}", file=sys.stderr)
        return False

    search_path = skill_base_path / operation
    if not search_path.exists():
        return False

    # Search for matching scripts using substring matching
    matching_scripts = list(search_path.glob(f"*{action}*.ps1"))
    return len(matching_scripts) > 0


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--list-available",
        action="store_true",
        help="List all available skills instead of checking for a specific one",
    )
    group.add_argument(
        "--operation",
        choices=sorted(VALID_OPERATIONS),
        help="The operation type to check",
    )

    parser.add_argument(
        "--action",
        help="The action name to check for (uses substring matching)",
    )

    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory (defaults to auto-detection)",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point. Returns exit code.

    Returns:
        0 on success, 1 if skill not found or invalid params, 2 on unexpected error.
    """
    try:
        args = parse_args()

        # Determine project root
        project_root = args.project_root or _PROJECT_ROOT

        # Validate project root exists
        if not project_root.exists():
            print(f"ERROR: Project root does not exist: {project_root}", file=sys.stderr)
            return 1

        # Get skill base path with validation
        skill_base_path = get_skill_base_path(project_root)

        if args.list_available:
            if not skill_base_path.exists():
                print(f"ERROR: Skill path does not exist: {skill_base_path}", file=sys.stderr)
                return 1
            list_available_skills(skill_base_path)
            return 0

        # Check mode requires both operation and action
        if not args.action:
            print("ERROR: --action is required when checking for a skill", file=sys.stderr)
            return 1

        # Validate the operation path is within the expected directory
        try:
            validate_safe_path(args.operation, skill_base_path)
        except (ValueError, FileNotFoundError):
            # Path validation may fail if directory does not exist yet
            pass

        if check_skill_exists(skill_base_path, args.operation, args.action):
            print("true")
            return 0
        else:
            print("false")
            return 1

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
