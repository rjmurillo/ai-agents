#!/usr/bin/env python3
"""Create new slash command with frontmatter template.

Automates slash command file creation with proper frontmatter structure.
Generates a template file that passes initial validation.

EXIT CODES (ADR-035):
    0 - Success: Command file created
    1 - Error: Invalid input, file exists, or creation failed
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def validate_name(name: str) -> bool:
    """Validate name contains only safe characters (CWE-22 prevention)."""
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", name))


def create_slash_command(name: str, namespace: str | None = None) -> int:
    """Create a new slash command template file.

    Returns exit code: 0 on success, 1 on failure.
    """
    if not validate_name(name):
        print(
            "Error: Name must contain only alphanumeric characters, hyphens, or underscores",
            file=sys.stderr,
        )
        return 1

    if namespace and not validate_name(namespace):
        print(
            "Error: Namespace must contain only alphanumeric characters, hyphens, or underscores",
            file=sys.stderr,
        )
        return 1

    base_dir = Path(".claude/commands")
    if namespace:
        file_path = base_dir / namespace / f"{name}.md"
    else:
        file_path = base_dir / f"{name}.md"

    if file_path.exists():
        print(f"Error: File already exists: {file_path}", file=sys.stderr)
        return 1

    directory = file_path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(
            f"Error: Failed to create commands directory '{directory}': {e}\n"
            "Check permissions, disk space, and path validity",
            file=sys.stderr,
        )
        return 1

    template = f"""---
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
            raise OSError("File write succeeded but file does not exist")
    except OSError as e:
        print(
            f"Error: Failed to write command file '{file_path}': {e}\n"
            "Check disk space, file locks, and filesystem health",
            file=sys.stderr,
        )
        return 1

    print(f"[PASS] Created: {file_path}")
    print(f"\nNext steps:")
    print(f"  1. Edit frontmatter (description, argument-hint, allowed-tools)")
    print(f"  2. Write prompt body")
    print(f"  3. Run: python3 .claude/skills/slashcommandcreator/scripts/validate_slash_command.py --path {file_path}")
    print(f"  4. Test: /{name} [arguments]")

    return 0


def main() -> int:
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Create new slash command with frontmatter template")
    parser.add_argument("--name", required=True, help="Command name (e.g., security-audit)")
    parser.add_argument("--namespace", help="Optional namespace (e.g., git, memory)")
    args = parser.parse_args()

    return create_slash_command(args.name, args.namespace)


if __name__ == "__main__":
    sys.exit(main())
