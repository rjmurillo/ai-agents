#!/usr/bin/env python3
"""Validate skill files follow atomic format and naming convention.

Enforces ADR-017 skill format requirements:
- One skill per file (no bundled skills)
- Files with ## Skill- headers are flagged as bundled format
- Files must NOT use 'skill-' prefix (use {domain}-{description} format)

EXIT CODES:
  0  - Success: All skill files follow atomic format and naming convention
  1  - Error: Bundled format or naming violations detected (CI mode only)

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SKILL_HEADER_RE = re.compile(r"(?m)^## Skill-[A-Za-z]+-[0-9]+:")


def get_staged_memory_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [
        f.strip()
        for f in result.stdout.splitlines()
        if f.strip().startswith(".serena/memories/")
        and f.strip().endswith(".md")
        and not re.search(r"skills-.*-index\.md$", f.strip())
    ]


def get_files_to_check(
    path: str,
    ci: bool,
    staged_only: bool,
    changed_files: list[str],
) -> list[Path]:
    if changed_files:
        candidates = [
            f
            for f in changed_files
            if f.startswith(".serena/memories/")
            and f.endswith(".md")
            and not re.search(r"skills-.*-index\.md$", f)
        ]
        if not candidates:
            print("No skill files in changed files list. Skipping format validation.")
            return []
        return [p for f in candidates if (p := Path(f)).exists()]

    if staged_only:
        staged = get_staged_memory_files()
        if not staged:
            print("No skill files staged. Skipping format validation.")
            return []
        return [p for f in staged if (p := Path(f)).exists()]

    # Check all skill files
    mem_path = Path(path)
    if not mem_path.exists():
        return []
    return [
        f
        for f in mem_path.glob("*.md")
        if not re.match(r"^skills-.*-index\.md$", f.name)
        and f.name != "memory-index.md"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate skill files follow atomic format"
    )
    parser.add_argument(
        "--path", default=".serena/memories", help="Path to memories directory"
    )
    parser.add_argument("--ci", action="store_true", help="CI mode (strict, exit 1 on failure)")
    parser.add_argument("--staged-only", action="store_true", help="Only check staged files")
    parser.add_argument("--changed-files", nargs="*", default=[], help="Specific files to check")
    args = parser.parse_args(argv)

    files = get_files_to_check(args.path, args.ci, args.staged_only, args.changed_files)
    if not files:
        print("No skill files found to validate.")
        return 0

    print("Validating skill format (ADR-017: one skill per file)...")

    bundled_files: list[tuple[str, int]] = []
    prefix_violations: list[str] = []

    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError:
            continue

        matches = SKILL_HEADER_RE.findall(content)
        if len(matches) > 1:
            print(f"  BUNDLED: {file_path.name} contains {len(matches)} skills")
            bundled_files.append((file_path.name, len(matches)))

        if file_path.name.startswith("skill-") and not file_path.name.endswith(
            "-observations.md"
        ):
            print(f"  PREFIX: {file_path.name} uses invalid 'skill-' prefix")
            prefix_violations.append(file_path.name)

    print()

    has_issues = False

    if bundled_files:
        has_issues = True
        print("=== Bundled Format Detected ===")
        print("The following files contain multiple skills:")
        for name, count in bundled_files:
            print(f"  - {name}: {count} skills")
        print()
        print("ADR-017 requires ONE skill per file. No exceptions.")
        print("Split bundled skills into separate atomic files.")
        print()

    if prefix_violations:
        has_issues = True
        print("=== Invalid Naming Convention ===")
        print("The following files use the deprecated 'skill-' prefix:")
        for name in prefix_violations:
            print(f"  - {name}")
        print()
        print("ADR-017 requires {domain}-{description} naming (no 'skill-' prefix).")
        print("Rename files to use domain prefix (e.g., pr-001-reviewer-enumeration.md).")
        print()

    if has_issues:
        if args.ci:
            print("Result: FAILED")
            return 1
        print("Result: WARNING (non-blocking for local development)")
        return 0

    print("Result: PASSED - All skill files follow atomic format and naming convention")
    return 0


if __name__ == "__main__":
    sys.exit(main())
