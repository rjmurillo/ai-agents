#!/usr/bin/env python3
"""Detect PowerShell files without corresponding test files.

Non-blocking WARNING that detects .ps1 files without corresponding .Tests.ps1 files.
Helps identify test coverage gaps before they cause QA failures.

EXIT CODES:
  0  - Success: Detection completed (gaps may exist as warnings)
  1  - Error: Could not find git repo root

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_IGNORE_PATTERNS = [
    r"\.Tests\.ps1$",
    r"tests?[/\\]",
    r"build[/\\]",
    r"\.github[/\\]",
    r"install.*\.ps1$",
    r"Common\.psm1$",
    r"AIReviewCommon\.psm1$",
]


def get_repo_root(start_dir: str = ".") -> Path | None:
    result = subprocess.run(
        ["git", "-C", start_dir, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def load_ignore_patterns(ignore_file: str) -> list[str]:
    path = Path(ignore_file)
    if not path.exists():
        return []
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            patterns.append(stripped)
    return patterns


def get_staged_ps1_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    files = [
        f.strip()
        for f in result.stdout.splitlines()
        if f.strip().endswith(".ps1") and not f.strip().endswith(".Tests.ps1")
    ]
    return files


def get_all_ps1_files(repo_root: Path) -> list[str]:
    files: list[str] = []
    for ps1 in repo_root.rglob("*.ps1"):
        rel = str(ps1.relative_to(repo_root)).replace("\\", "/")
        if ".git/" in rel or "node_modules/" in rel:
            continue
        if ps1.name.endswith(".Tests.ps1"):
            continue
        files.append(rel)
    return files


def should_ignore(file_path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if re.search(pattern, file_path):
            return True
    return False


def find_test_file(file_path: str, repo_root: Path) -> bool:
    stem = Path(file_path).stem
    file_dir = str(Path(file_path).parent)

    test_name = f"{stem}.Tests.ps1"

    # Check same directory
    same_dir = repo_root / file_dir / test_name if file_dir != "." else repo_root / test_name
    if same_dir.exists():
        return True

    # Check tests/ subdirectory
    tests_dir = repo_root / file_dir / "tests" / test_name if file_dir != "." else repo_root / "tests" / test_name
    if tests_dir.exists():
        return True

    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect PowerShell files without test coverage")
    parser.add_argument("--path", default=".", help="Root path to scan (default: current directory)")
    parser.add_argument("--staged-only", action="store_true", help="Only check git-staged files")
    parser.add_argument("--ignore-file", default="", help="Path to file with ignore patterns")
    args = parser.parse_args(argv)

    repo_root = get_repo_root(args.path)
    if not repo_root:
        print(f"ERROR: Could not find git repo root from: {args.path}", file=sys.stderr)
        return 1

    ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)
    if args.ignore_file:
        ignore_patterns.extend(load_ignore_patterns(args.ignore_file))

    if args.staged_only:
        files_to_check = get_staged_ps1_files(repo_root)
    else:
        files_to_check = get_all_ps1_files(repo_root)

    if not files_to_check:
        print("No PowerShell files to check for test coverage")
        return 0

    missing_tests: list[tuple[str, str]] = []

    for file_path in files_to_check:
        if should_ignore(file_path, ignore_patterns):
            continue

        if not find_test_file(file_path, repo_root):
            stem = Path(file_path).stem
            file_dir = str(Path(file_path).parent)
            expected = f"{file_dir}/{stem}.Tests.ps1" if file_dir != "." else f"{stem}.Tests.ps1"
            missing_tests.append((file_path, expected))

    if missing_tests:
        print()
        print("WARNING: Detected PowerShell files without test coverage")
        print("  Consider adding test files to improve quality and catch regressions")
        print()
        for file_path, expected in missing_tests:
            print(f"  {file_path}")
            print(f"    -> Missing: {expected}")
        print()
        print("This is a WARNING (non-blocking). To suppress, add patterns to ignore file.")
        return 0

    print("All PowerShell files have corresponding test coverage")
    return 0


if __name__ == "__main__":
    sys.exit(main())
