#!/usr/bin/env python3
"""Maintain explicit PR-to-branch mapping for cross-session verification.

Stores a JSON mapping of PR numbers to branch names in a Serena memory file.
Enables automated branch verification during multi-PR sessions to prevent
cross-PR commits (root cause from PR #669 retrospective).

EXIT CODES:
  0  - Success: Operation completed
  1  - Error: Invalid arguments or validation failure
  2  - Error: Unexpected error
  3  - Error: External dependency failure (file system, git)

See: ADR-035 Exit Code Standardization, Issue #683
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

MEMORY_FILENAME = "pr-branch-mapping.md"
MEMORY_RELATIVE_PATH = f".serena/memories/{MEMORY_FILENAME}"


@dataclass
class PRBranchEntry:
    """A single PR-to-branch mapping entry."""

    pr_number: int
    branch_name: str
    created_at: str
    status: str = "open"
    last_session: str = ""


@dataclass
class CurrentSession:
    """Tracks the active session context."""

    session_id: str
    pr_number: int
    branch_name: str


@dataclass
class PRBranchMapping:
    """Full PR-to-branch mapping state."""

    mappings: list[PRBranchEntry] = field(default_factory=list)
    current_session: CurrentSession | None = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        result: dict = {"mappings": [asdict(m) for m in self.mappings]}
        if self.current_session:
            result["current_session"] = asdict(self.current_session)
        return result


def load_mapping(project_root: Path) -> PRBranchMapping:
    """Load PR-branch mapping from the Serena memory file.

    Args:
        project_root: Repository root directory.

    Returns:
        Parsed mapping, or empty mapping if file does not exist.
    """
    memory_path = project_root / MEMORY_RELATIVE_PATH
    if not memory_path.exists():
        return PRBranchMapping()

    content = memory_path.read_text(encoding="utf-8")
    json_str = _extract_json_block(content)
    if not json_str:
        return PRBranchMapping()

    data = json.loads(json_str)
    entries = [PRBranchEntry(**m) for m in data.get("mappings", [])]

    current = None
    if "current_session" in data and data["current_session"]:
        current = CurrentSession(**data["current_session"])

    return PRBranchMapping(mappings=entries, current_session=current)


def save_mapping(project_root: Path, mapping: PRBranchMapping) -> None:
    """Write PR-branch mapping to the Serena memory file.

    Args:
        project_root: Repository root directory.
        mapping: The mapping state to persist.
    """
    memory_path = project_root / MEMORY_RELATIVE_PATH
    memory_path.parent.mkdir(parents=True, exist_ok=True)

    json_str = json.dumps(mapping.to_dict(), indent=2)
    content = _build_memory_content(json_str)
    memory_path.write_text(content, encoding="utf-8")


def add_mapping(
    mapping: PRBranchMapping,
    pr_number: int,
    branch_name: str,
    session_id: str = "",
) -> PRBranchMapping:
    """Add or update a PR-to-branch mapping entry.

    If the PR number already exists, updates the entry. Otherwise adds a new one.

    Args:
        mapping: Current mapping state.
        pr_number: The pull request number.
        branch_name: The git branch name.
        session_id: Optional session identifier.

    Returns:
        Updated mapping with the new/updated entry.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    existing = _find_entry(mapping, pr_number=pr_number)
    if existing:
        existing.branch_name = branch_name
        existing.last_session = session_id
    else:
        entry = PRBranchEntry(
            pr_number=pr_number,
            branch_name=branch_name,
            created_at=now,
            last_session=session_id,
        )
        mapping.mappings.append(entry)

    mapping.current_session = CurrentSession(
        session_id=session_id,
        pr_number=pr_number,
        branch_name=branch_name,
    )
    return mapping


def get_branch_for_pr(mapping: PRBranchMapping, pr_number: int) -> str | None:
    """Look up the branch name for a given PR number.

    Args:
        mapping: Current mapping state.
        pr_number: The pull request number to look up.

    Returns:
        Branch name if found, None otherwise.
    """
    entry = _find_entry(mapping, pr_number=pr_number)
    return entry.branch_name if entry else None


def get_pr_for_branch(mapping: PRBranchMapping, branch_name: str) -> int | None:
    """Look up the PR number for a given branch name.

    Args:
        mapping: Current mapping state.
        branch_name: The git branch name to look up.

    Returns:
        PR number if found, None otherwise.
    """
    entry = _find_entry(mapping, branch_name=branch_name)
    return entry.pr_number if entry else None


def validate_branch_pr_consistency(
    mapping: PRBranchMapping,
    current_branch: str | None = None,
) -> tuple[bool, str]:
    """Check that the current branch matches the active PR context.

    Args:
        mapping: Current mapping state.
        current_branch: Override for current branch (uses git if None).

    Returns:
        Tuple of (is_consistent, message).
    """
    if not mapping.current_session:
        return True, "No active session context"

    if current_branch is None:
        current_branch = _get_current_branch()
        if current_branch is None:
            return False, "Could not determine current git branch"

    expected = mapping.current_session.branch_name
    if current_branch != expected:
        return False, (
            f"Branch mismatch: current={current_branch}, "
            f"expected={expected} (PR #{mapping.current_session.pr_number})"
        )

    return True, "Branch matches active PR context"


def remove_merged_entries(mapping: PRBranchMapping) -> int:
    """Remove entries with status 'merged' or 'closed'.

    Args:
        mapping: Current mapping state (modified in place).

    Returns:
        Number of entries removed.
    """
    original_count = len(mapping.mappings)
    mapping.mappings = [
        m for m in mapping.mappings if m.status not in ("merged", "closed")
    ]
    return original_count - len(mapping.mappings)


# --- Private helpers ---


def _find_entry(
    mapping: PRBranchMapping,
    pr_number: int | None = None,
    branch_name: str | None = None,
) -> PRBranchEntry | None:
    """Find a mapping entry by PR number or branch name."""
    for entry in mapping.mappings:
        if pr_number is not None and entry.pr_number == pr_number:
            return entry
        if branch_name is not None and entry.branch_name == branch_name:
            return entry
    return None


def _extract_json_block(content: str) -> str | None:
    """Extract JSON from a fenced code block in markdown."""
    in_block = False
    lines: list[str] = []
    for line in content.splitlines():
        if line.strip().startswith("```json"):
            in_block = True
            continue
        if in_block and line.strip() == "```":
            break
        if in_block:
            lines.append(line)
    return "\n".join(lines) if lines else None


def _build_memory_content(json_str: str) -> str:
    """Build the Serena memory markdown file content."""
    return (
        "# PR-to-Branch Mapping\n"
        "\n"
        "**Importance**: HIGH\n"
        "**Updated**: " + datetime.now(UTC).strftime("%Y-%m-%d") + "\n"
        "**Applies To**: session protocol, git hooks\n"
        "\n"
        "Explicit mapping of PR numbers to branch names.\n"
        "Prevents cross-PR commits during multi-PR sessions (Issue #683).\n"
        "\n"
        "```json\n"
        f"{json_str}\n"
        "```\n"
    )


def _get_current_branch() -> str | None:
    """Get the current git branch name."""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Manage PR-to-branch mapping in Serena memory.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory (default: cwd).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    add_cmd = sub.add_parser("add", help="Add or update a PR-branch mapping.")
    add_cmd.add_argument("--pr", type=int, required=True, help="PR number.")
    add_cmd.add_argument("--branch", required=True, help="Branch name.")
    add_cmd.add_argument("--session", default="", help="Session identifier.")

    query_cmd = sub.add_parser("query", help="Look up a mapping.")
    query_grp = query_cmd.add_mutually_exclusive_group(required=True)
    query_grp.add_argument("--pr", type=int, help="Look up branch by PR number.")
    query_grp.add_argument("--branch", help="Look up PR by branch name.")

    sub.add_parser("validate", help="Check branch/PR consistency.")
    sub.add_parser("list", help="List all mappings.")
    sub.add_parser("cleanup", help="Remove merged/closed entries.")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Returns:
        0 on success, 1 on validation/argument error, 2 on unexpected error,
        3 on external dependency failure.
    """
    try:
        args = _parse_args(argv)
        project_root: Path = args.project_root.resolve()

        mapping = load_mapping(project_root)

        if args.command == "add":
            add_mapping(mapping, args.pr, args.branch, args.session)
            save_mapping(project_root, mapping)
            print(f"Added mapping: PR #{args.pr} -> {args.branch}")
            return 0

        if args.command == "query":
            if args.pr is not None:
                branch = get_branch_for_pr(mapping, args.pr)
                if branch:
                    print(branch)
                    return 0
                print(f"No mapping found for PR #{args.pr}", file=sys.stderr)
                return 1
            pr = get_pr_for_branch(mapping, args.branch)
            if pr is not None:
                print(pr)
                return 0
            print(f"No mapping found for branch '{args.branch}'", file=sys.stderr)
            return 1

        if args.command == "validate":
            is_ok, msg = validate_branch_pr_consistency(mapping)
            print(msg)
            return 0 if is_ok else 1

        if args.command == "list":
            if not mapping.mappings:
                print("No mappings stored.")
                return 0
            for entry in mapping.mappings:
                print(f"PR #{entry.pr_number} -> {entry.branch_name} ({entry.status})")
            return 0

        if args.command == "cleanup":
            removed = remove_merged_entries(mapping)
            if removed > 0:
                save_mapping(project_root, mapping)
            print(f"Removed {removed} merged/closed entries.")
            return 0

    except json.JSONDecodeError as exc:
        print(f"ERROR: Corrupt mapping file: {exc}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 1
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
