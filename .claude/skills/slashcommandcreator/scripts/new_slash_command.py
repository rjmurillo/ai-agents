#!/usr/bin/env python3
"""Create new slash command with frontmatter template.

Automates slash command file creation with proper frontmatter structure.
Generates a template file that passes initial validation.

Exit codes follow ADR-035:
    0 - Success: Command file created
    1 - Error: Invalid input, file exists, or creation failed
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _validate_name(name: str) -> bool:
    """Validate name contains only safe characters (CWE-22 prevention)."""
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", name))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a new slash command with frontmatter template.",
    )
    parser.add_argument(
        "--name", required=True, help="Command name (e.g., security-audit)",
    )
    parser.add_argument(
        "--namespace",
        default="",
        help="Optional namespace (e.g., git, memory)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    name: str = args.name
    namespace: str = args.namespace

    # Validate input to prevent path traversal (CWE-22)
    if not _validate_name(name):
        print(
            "Error: Name must contain only alphanumeric characters, "
            "hyphens, or underscores",
            file=sys.stderr,
        )
        return 1

    if namespace and not _validate_name(namespace):
        print(
            "Error: Namespace must contain only alphanumeric characters, "
            "hyphens, or underscores",
            file=sys.stderr,
        )
        return 1

    # Determine file path
    base_dir = Path(".claude/commands")
    if namespace:
        file_path = base_dir / namespace / f"{name}.md"
    else:
        file_path = base_dir / f"{name}.md"

    # Check if file exists
    if file_path.exists():
        print(f"Error: File already exists: {file_path}", file=sys.stderr)
        return 1

    # Ensure directory exists
    directory = file_path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(
            f"Error: Failed to create commands directory '{directory}': {exc}\n"
            f"Check permissions, disk space, and path validity",
            file=sys.stderr,
        )
        return 1

    # Generate frontmatter template
    template = f"""\
---
description: Use when Claude needs to [FILL IN: when to use this command]
argument-hint: <arg>
allowed-tools: []
---

# {name} Command

[FILL IN: Detailed prompt instructions]

## Arguments

- `$ARGUMENTS`: [FILL IN: what argument is expected]

## Example

```text
/{name} [example argument]
```
"""

    try:
        file_path.write_text(template, encoding="utf-8")
        if not file_path.exists():
            print(
                "Error: File write succeeded but file does not exist",
                file=sys.stderr,
            )
            return 1
    except OSError as exc:
        print(
            f"Error: Failed to write command file '{file_path}': {exc}\n"
            f"Check disk space, file locks, and filesystem health",
            file=sys.stderr,
        )
        return 1

    print(f"[PASS] Created: {file_path}")
    print("\nNext steps:")
    print("  1. Edit frontmatter (description, argument-hint, allowed-tools)")
    print("  2. Write prompt body")
    print(
        f"  3. Run: python3 .claude/skills/slashcommandcreator/scripts/"
        f"validate_slash_command.py --path {file_path}"
    )
    print(f"  4. Test: /{name} [arguments]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
