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
VALID_EXTENSIONS = frozenset({".md", ".ps1", ".psm1"})


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
            timeout=30,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError(f"Could not find git repo root from: {start_dir}")
        return Path(result.stdout.strip())
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Timeout finding git repo root from: {start_dir}") from None


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

    Args:
        repo_root: Repository root path.

    Returns:
        List of file paths (relative to repo root).
    """
    files = []
    for ext in VALID_EXTENSIONS:
        for path in repo_root.rglob(f"*{ext}"):
            # Skip .git and node_modules directories
            rel_path = path.relative_to(repo_root)
            if ".git" in rel_path.parts or "node_modules" in rel_path.parts:
                continue
            files.append(str(rel_path).replace("\\", "/"))
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
    command_pattern = re.compile(r"gh\\s\+(\w+)")
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

    capability_gaps: set[str] = set()

    for v in violations:
        print(f"  {v.file}:{v.line} - matches '{v.pattern}'")
        # Extract the specific command for capability tracking
        match = re.search(r"gh\\s\+(\w+)", v.pattern)
        if match:
            capability_gaps.add(match.group(1))

    print()
    print("Missing skill capabilities detected:")
    for gap in sorted(capability_gaps):
        print(f"  - gh {gap} (consider adding to .claude/skills/github/)")

    print()
    print("REMINDER: Use GitHub skills for better error handling, consistency, and auditability.")
    print("  Before using raw 'gh' commands, check:")
    print("    Get-ChildItem .claude/skills/github/scripts -Recurse")
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
