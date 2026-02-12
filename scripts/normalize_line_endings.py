#!/usr/bin/env python3
"""Normalize line endings in the repository to LF.

Applies .gitattributes rules to all existing files by renormalizing line endings.
Run once after updating .gitattributes to enforce LF line endings repository-wide.

EXIT CODES:
  0  - Success: Line endings normalized (or already normalized)
  1  - Error: Not a git repository or normalization failed

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
    )


def is_git_repository() -> bool:
    result = run_git("rev-parse", "--is-inside-work-tree")
    return result.returncode == 0


def get_line_ending_stats(stage: str) -> dict[str, int]:
    print(f"\n[{stage}] Line Ending Statistics:")
    result = run_git("ls-files", "--eol")
    if result.returncode != 0:
        print("  Failed to get line ending info")
        return {"index_lf": 0, "index_crlf": 0, "working_lf": 0, "working_crlf": 0}

    lines = result.stdout.splitlines()
    index_crlf = sum(1 for line in lines if "i/crlf" in line)
    index_lf = sum(1 for line in lines if "i/lf" in line)
    working_crlf = sum(1 for line in lines if "w/crlf" in line)
    working_lf = sum(1 for line in lines if "w/lf" in line)

    print(f"  Index (staged):      {index_lf} LF, {index_crlf} CRLF")
    print(f"  Working directory:   {working_lf} LF, {working_crlf} CRLF")

    return {
        "index_lf": index_lf,
        "index_crlf": index_crlf,
        "working_lf": working_lf,
        "working_crlf": working_crlf,
    }


def save_line_ending_audit(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = run_git("ls-files", "--eol")
    output_path.write_text(result.stdout, encoding="utf-8")
    print(f"Saved line ending audit to: {output_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize line endings to LF")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without making changes",
    )
    args = parser.parse_args(argv)

    if not is_git_repository():
        print("ERROR: Current directory is not a Git repository.", file=sys.stderr)
        return 1

    print("\nLine Ending Normalization Script")
    print("=================================")

    before_stats = get_line_ending_stats("BEFORE")
    before_audit = Path(".agents/analysis/line-endings-before.txt")
    save_line_ending_audit(before_audit)

    if before_stats["index_crlf"] == 0:
        print("\nNo line ending normalization needed. All files already use LF.")
        return 0

    print("\nNormalizing line endings...")

    if args.dry_run:
        print(f"  [DRY-RUN] Would normalize {before_stats['index_crlf']} files from CRLF to LF")
        return 0

    print("  [1/2] Re-adding files with normalized line endings...")
    result = run_git("add", "--renormalize", ".")
    if result.returncode != 0:
        print(f"ERROR: git add --renormalize failed: {result.stderr}", file=sys.stderr)
        return 1

    print("  [2/2] Verifying normalization...")
    after_stats = get_line_ending_stats("AFTER")

    after_audit = Path(".agents/analysis/line-endings-after.txt")
    save_line_ending_audit(after_audit)

    print(f"\nNormalization complete!")
    print(f"  Normalized {before_stats['index_crlf']} files from CRLF to LF")

    print("\nNext Steps:")
    print("  1. Review the changes: git diff --stat")
    print(f"  2. Compare audits: diff {before_audit} {after_audit}")
    print("  3. Commit: git commit -m 'chore: normalize line endings to LF'")

    return 0


if __name__ == "__main__":
    sys.exit(main())
