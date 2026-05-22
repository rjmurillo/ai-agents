#!/usr/bin/env python3
"""Fix malformed markdown code fence closings.

Scans markdown files and repairs closing fences that incorrectly include
language identifiers (```python instead of ```).

EXIT CODES (ADR-035):
    0 - Success: Fences fixed or no issues found
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def repair_markdown_fences(content: str) -> str:
    """Repair malformed markdown code fence closings.

    Detects closing fences that incorrectly include language identifiers
    and inserts proper closing fences before them.
    """
    lines = re.split(r"\r?\n", content)
    result: list[str] = []
    in_code_block = False
    code_block_indent = ""

    for line in lines:
        opening_match = re.match(r"^(\s*)```(\w+)", line)
        closing_match = re.match(r"^(\s*)```\s*$", line)

        if opening_match:
            if in_code_block:
                result.append(code_block_indent + "```")
            result.append(line)
            code_block_indent = opening_match.group(1)
            in_code_block = True
        elif closing_match:
            result.append(line)
            in_code_block = False
            code_block_indent = ""
        else:
            result.append(line)

    if in_code_block:
        result.append(code_block_indent + "```")

    return "\n".join(result)


def fix_fences(directories: list[str], pattern: str = "*.md") -> int:
    """Scan directories for markdown files and fix malformed fences.

    Returns the number of files fixed.
    """
    total_fixed = 0

    for directory in directories:
        dir_path = Path(directory)
        if not dir_path.exists():
            print(f"Warning: Directory does not exist: {directory}", file=sys.stderr)
            continue

        for md_file in dir_path.rglob(pattern):
            if not md_file.is_file():
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError:
                continue

            if not content:
                continue

            fixed_content = repair_markdown_fences(content)
            if content != fixed_content:
                md_file.write_text(fixed_content, encoding="utf-8")
                total_fixed += 1

    return total_fixed


def main() -> int:
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Fix malformed markdown code fence closings")
    parser.add_argument(
        "--directories",
        nargs="+",
        default=["vs-code-agents", "copilot-cli"],
        help="Directories to scan",
    )
    parser.add_argument("--pattern", default="*.md", help="File pattern to match")
    args = parser.parse_args()

    total_fixed = fix_fences(args.directories, args.pattern)

    if total_fixed == 0:
        print("No files needed fixing")
    else:
        print(f"\nTotal: fixed {total_fixed} file(s)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
