#!/usr/bin/env python3
"""Validate SKILL.md files do not exceed size limits.

Enforces prompt size limits for skill files to prevent token bloat,
maintainability issues, and processing overhead. Skills exceeding
the limit should use progressive disclosure (references/, modules/).

Size limits:
    - SKILL.md: 500 lines (warning at 300)
    - Exception: documented in frontmatter with 'size-exception: true'

Exit codes follow ADR-035:
    0 - Success: All skill files within size limits
    1 - Error: One or more files exceed limit (CI mode only)
    2 - Config error (path not found)

Related: Issue #676 (Skill Prompt Size Limits)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Size thresholds (lines)
SKILL_SIZE_LIMIT: int = 500
SKILL_SIZE_WARNING: int = 300


@dataclass
class SizeCheckResult:
    """Result of checking a single SKILL.md file size."""

    file_path: str
    line_count: int
    has_exception: bool = False
    passed: bool = True
    warning: bool = False
    errors: list[str] = field(default_factory=list)


def has_size_exception(content: str) -> bool:
    """Check if frontmatter declares a size exception."""
    if not content.startswith("---"):
        return False

    lines = content.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            frontmatter = "\n".join(lines[1:i])
            return bool(re.search(r"^size-exception:\s*true", frontmatter, re.MULTILINE))
    return False


def check_skill_size(file_path: Path) -> SizeCheckResult:
    """Check a single SKILL.md file against size limits."""
    try:
        relative = file_path.relative_to(Path.cwd())
    except ValueError:
        relative = file_path

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return SizeCheckResult(
            file_path=str(relative),
            line_count=0,
            passed=False,
            errors=["File is unreadable"],
        )

    line_count = len(content.splitlines())
    exception = has_size_exception(content)

    result = SizeCheckResult(
        file_path=str(relative),
        line_count=line_count,
        has_exception=exception,
    )

    if line_count > SKILL_SIZE_LIMIT:
        if exception:
            result.warning = True
        else:
            result.passed = False
            result.errors.append(
                f"SKILL.md exceeds {SKILL_SIZE_LIMIT} lines ({line_count} lines). "
                f"Refactor using progressive disclosure: move details to references/, "
                f"modules/, or scripts/. Add 'size-exception: true' to frontmatter "
                f"if overage is justified."
            )
    elif line_count > SKILL_SIZE_WARNING:
        result.warning = True

    return result


def get_staged_skill_files() -> list[Path]:
    """Get staged SKILL.md files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if result.returncode != 0:
        return []

    files: list[Path] = []
    for line in result.stdout.strip().split("\n"):
        if re.search(r"\.claude/skills/.*/SKILL\.md$", line):
            path = Path(line)
            if path.exists():
                files.append(path)
    return files


def get_skill_files(
    path: str,
    staged_only: bool = False,
    changed_files: list[str] | None = None,
) -> list[Path]:
    """Get list of SKILL.md files to validate."""
    if changed_files:
        skill_files = [
            f for f in changed_files
            if re.search(r"\.claude/skills/.*/SKILL\.md$", f)
        ]
        if not skill_files:
            return []
        return [Path(f) for f in skill_files if Path(f).exists()]

    if staged_only:
        return get_staged_skill_files()

    target = Path(path)
    if not target.exists():
        return []

    if target.is_file() and target.name == "SKILL.md":
        return [target]

    return sorted(target.rglob("SKILL.md"))


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate SKILL.md files against size limits.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("SKILL_PATH", ".claude/skills"),
        help="Path to SKILL.md file or directory (default: .claude/skills)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit non-zero on validation failure",
    )
    parser.add_argument(
        "--staged-only",
        action="store_true",
        default=os.environ.get("STAGED_ONLY", "").lower() in ("true", "1"),
        help="Only check staged files",
    )
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Explicit list of file paths to check",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=SKILL_SIZE_LIMIT,
        help=f"Maximum lines allowed (default: {SKILL_SIZE_LIMIT})",
    )
    parser.add_argument(
        "--warn",
        type=int,
        default=SKILL_SIZE_WARNING,
        help=f"Warning threshold in lines (default: {SKILL_SIZE_WARNING})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Allow overriding thresholds via CLI
    global SKILL_SIZE_LIMIT, SKILL_SIZE_WARNING  # noqa: PLW0603
    SKILL_SIZE_LIMIT = args.limit
    SKILL_SIZE_WARNING = args.warn

    print("Validating skill prompt sizes...")

    files = get_skill_files(
        path=args.path,
        staged_only=args.staged_only,
        changed_files=args.changed_files,
    )

    if not files:
        print("No SKILL.md files found to validate.")
        return 0

    print(f"Found {len(files)} SKILL.md file(s) to check.\n")

    pass_count = 0
    warn_count = 0
    fail_count = 0

    for file_path in files:
        result = check_skill_size(file_path)

        if not result.passed:
            fail_count += 1
            print(f"  [FAIL] {result.file_path} ({result.line_count} lines)")
            for error in result.errors:
                print(f"    {error}")
        elif result.warning:
            warn_count += 1
            if result.has_exception:
                print(
                    f"  [EXCEPTION] {result.file_path} ({result.line_count} lines)"
                    " - size-exception declared"
                )
            else:
                print(f"  [WARN] {result.file_path} ({result.line_count} lines)")
            pass_count += 1
        else:
            pass_count += 1

    print()
    print("=" * 40)
    print("Skill Size Summary")
    print("=" * 40)
    print(f"  Total:    {len(files)}")
    print(f"  Passed:   {pass_count}")
    print(f"  Warnings: {warn_count}")
    print(f"  Failed:   {fail_count}")
    print(f"  Limit:    {SKILL_SIZE_LIMIT} lines")
    print()

    if fail_count > 0:
        print("Fix oversized skills by refactoring to progressive disclosure:")
        print("  - Move reference docs to references/")
        print("  - Extract scripts to scripts/")
        print("  - Use modules/ for reusable logic")
        print("  - Add 'size-exception: true' to frontmatter if justified")

        if args.ci:
            return 1

        print("\nNot in CI mode. Continuing...")

    else:
        print("All skill files within size limits.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
