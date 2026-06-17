#!/usr/bin/env python3
"""Detect raw gh command usage when GitHub skills exist.

Non-blocking WARNING that detects raw `gh` commands in markdown and PowerShell files
when equivalent GitHub skill scripts exist in .claude/skills/github/.

This implements Phase 1 guardrail from Issue #230.

This is a Python port of Detect-SkillViolation.ps1 following ADR-042 migration.

EXIT CODES:
  0  - Success: Detection completed (violations may exist as warnings)
  1  - Error: Could not find git repo root or other fatal error
  2  - Error: Unexpected error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# Add project root to path for imports
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.utils.path_validation import validate_safe_path  # noqa: E402

# Patterns to detect raw gh usage
GH_PATTERNS = (
    re.compile(r"gh\s+pr\s+(create|merge|close|view|list|diff)"),
    re.compile(r"gh\s+issue\s+(create|close|view|list)"),
    re.compile(r"gh\s+api\s+"),
    re.compile(r"gh\s+repo\s+"),
)

# File extensions to check
VALID_EXTENSIONS = frozenset({".md", ".py", ".ps1", ".psm1"})

# Directories pruned from the full-tree walk.
#
# Performance contract (issue #2047 / #2010): a full-tree scan via --path or
# the default walk MUST finish well under the 60-second pytest subprocess
# timeout in tests/test_detect_skill_violation.py (and the 30-second
# new_pr.py validation budget). The prior walk used rglob over the whole
# tree and only filtered .git and node_modules AFTER the walk, so it still
# descended into and counted every file in the largest subtrees. Measured
# from the repo root: 50390 files, ~32s wall clock; .venv alone was 32171
# files and the .claude tree (which holds agent worktrees, each a full repo
# copy) was 17074.
#
# These directories hold no source the scanner needs and dominate the cost
# as the checkout grows. os.walk prunes by directory basename, so the bare
# name "worktrees" prunes the .claude/worktrees subtree and ".worktrees"
# prunes the top-level git-worktree root (a 40+ checkout tree; #2047/#2621). When the repo
# grows, add hot directories here rather than widening the walk.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".worktrees",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "worktrees",
    }
)


@dataclass
class Violation:
    """Represents a skill violation found in a file."""

    file: str
    pattern: str
    line: int


def get_repo_root(start_dir: Path) -> Path:
    """Get the git repository root from a starting directory.

    Args:
        start_dir: Directory to start searching from.

    Returns:
        Path to the repository root.

    Raises:
        RuntimeError: If not in a git repository.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(start_dir), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Could not find git repo root from: {start_dir}") from exc

    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"Could not find git repo root from: {start_dir}")
    return Path(result.stdout.strip()).resolve()


def get_skills_dir(repo_root: Path) -> Path:
    """Get the GitHub skills directory.

    Args:
        repo_root: Repository root path.

    Returns:
        Path to the skills directory.
    """
    return repo_root / ".claude" / "skills" / "github" / "scripts"


def get_staged_files(repo_root: Path) -> list[str]:
    """Get list of staged files in the git repository.

    Args:
        repo_root: Repository root path.

    Returns:
        List of staged file paths (relative to repo root).
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return []
        files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
        return [f for f in files if Path(f).suffix in VALID_EXTENSIONS]
    except subprocess.TimeoutExpired:
        return []


def get_all_files(repo_root: Path) -> list[str]:
    """Get all relevant files in the repository.

    Walks the tree once with os.walk and prunes SKIP_DIRS in place so the
    walk never descends into the largest, source-free subtrees (.venv, agent
    worktrees, caches). See the SKIP_DIRS comment for the performance
    contract behind issue #2047 / #2010.

    Args:
        repo_root: Repository root path.

    Returns:
        List of file paths (relative to repo root), POSIX-separated.
    """
    files: list[str] = []
    for current_dir, dir_names, file_names in os.walk(repo_root):
        # Prune in place so os.walk does not descend into skipped subtrees.
        dir_names[:] = [d for d in dir_names if d not in SKIP_DIRS]
        for name in file_names:
            if Path(name).suffix not in VALID_EXTENSIONS:
                continue
            rel_path = Path(current_dir, name).relative_to(repo_root)
            files.append(rel_path.as_posix())
    return files


def check_file_for_violations(
    repo_root: Path,
    file_path: str,
) -> Violation | None:
    """Check a file for skill violations.

    Args:
        repo_root: Repository root path.
        file_path: File path relative to repo root.

    Returns:
        Violation if found, None otherwise.
    """
    try:
        full_path = validate_safe_path(file_path, repo_root)
    except (ValueError, FileNotFoundError):
        return None

    if not full_path.exists():
        return None

    try:
        content = full_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    for pattern in GH_PATTERNS:
        if pattern.search(content):
            # Find line number
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                if pattern.search(line):
                    return Violation(
                        file=file_path,
                        pattern=pattern.pattern,
                        line=i,
                    )
    return None


def detect_violations(
    repo_root: Path,
    files: Sequence[str],
) -> list[Violation]:
    """Detect skill violations in the given files.

    Args:
        repo_root: Repository root path.
        files: List of file paths to check.

    Returns:
        List of violations found.
    """
    violations = []
    for file_path in files:
        violation = check_file_for_violations(repo_root, file_path)
        if violation:
            violations.append(violation)
    return violations


def extract_capability_gaps(violations: list[Violation]) -> set[str]:
    """Extract capability gaps from violations.

    Args:
        violations: List of violations found.

    Returns:
        Set of gh commands that need skill implementations.
    """
    gaps: set[str] = set()
    # Pattern to extract the command (e.g., 'pr', 'issue', 'api') from violation patterns
    command_pattern = re.compile(r"gh\s+(\w+)")
    for v in violations:
        match = command_pattern.search(v.pattern)
        if match:
            gaps.add(match.group(1))
    return gaps


def report_violations(violations: list[Violation]) -> None:
    """Report violations to stdout.

    Args:
        violations: List of violations to report.
    """
    print()
    print("WARNING: Detected raw 'gh' command usage (skill violations)")
    print("  These commands indicate missing GitHub skill capabilities.")
    print("  Use .claude/skills/github/ scripts instead, or file an issue to add the capability.")
    print()

    for v in violations:
        print(f"  {v.file}:{v.line} - matches '{v.pattern}'")

    # Use the extract_capability_gaps function to identify missing skills
    capability_gaps = extract_capability_gaps(violations)

    print()
    print("Missing skill capabilities detected:")
    for gap in sorted(capability_gaps):
        print(f"  - gh {gap} (consider adding to .claude/skills/github/)")

    print()
    print("REMINDER: Use GitHub skills for better error handling, consistency, and auditability.")
    print("  Before using raw 'gh' commands, check:")
    print("    find .claude/skills/github/scripts -name '*.py'")
    print("  If the capability you need doesn't exist, create a skill script or file an issue.")
    print()
    print("See: .serena/memories/skill-usage-mandatory.md")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("."),
        help="Root path to scan (default: current directory)",
    )
    parser.add_argument(
        "--staged-only",
        action="store_true",
        help="Only check git-staged files",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output (exit code only)",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point. Returns exit code.

    Returns:
        0 on success, 1 on git error, 2 on unexpected error.
    """
    try:
        args = parse_args()

        # Get repo root
        try:
            repo_root = get_repo_root(args.path.resolve())
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        # Check if skills directory exists
        skills_dir = get_skills_dir(repo_root)
        if not skills_dir.exists():
            if not args.quiet:
                print(f"WARNING: GitHub skills directory not found: {skills_dir}", file=sys.stderr)
            return 0

        # Get files to check
        if args.staged_only:
            files = get_staged_files(repo_root)
        else:
            files = get_all_files(repo_root)

        if not files:
            if not args.quiet:
                print("No files to check for skill violations")
            return 0

        # Detect violations
        violations = detect_violations(repo_root, files)

        # Report results
        if violations:
            if not args.quiet:
                report_violations(violations)
            # Non-blocking: return success status (warning only)
            return 0
        else:
            if not args.quiet:
                print("No skill violations detected")
            return 0

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
