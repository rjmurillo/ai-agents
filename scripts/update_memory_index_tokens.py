#!/usr/bin/env python3
"""
Update token counts in memory-index.md.

Reads memory-index.md, finds markdown links to memory files,
counts tokens for each referenced file, and updates inline
token counts. Uses tiktoken cache for performance.

Gracefully degrades if tiktoken is not installed (warning only).

Exit codes per ADR-035:
  0 - Success (counts updated or already current)
  1 - Error (file not found, parse failure)
  2 - Warning (tiktoken not installed, counts skipped)
"""

import re
import sys
from pathlib import Path

# Graceful tiktoken import
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/memory/scripts"))
    from count_memory_tokens import get_memory_token_count
    HAS_TIKTOKEN = True
except (ImportError, SystemExit):
    HAS_TIKTOKEN = False


LINK_WITH_COUNT = re.compile(
    r'\[([^\]]+)\]\(([^)]+\.md)\)\s*\((\d+)\)'
)
LINK_WITHOUT_COUNT = re.compile(
    r'\[([^\]]+)\]\(([^)]+\.md)\)(?!\s*\(\d+\))'
)


def update_line(line: str, memories_dir: Path) -> str:
    """Update token counts for all memory links in a single line."""
    result = line

    # First pass: update existing counts
    for match in LINK_WITH_COUNT.finditer(line):
        link_text = match.group(1)
        link_target = match.group(2)
        old_count = int(match.group(3))

        file_path = memories_dir / link_target
        if not file_path.exists():
            continue

        new_count = get_memory_token_count(file_path)
        if new_count != old_count:
            old_str = f"[{link_text}]({link_target}) ({old_count})"
            new_str = f"[{link_text}]({link_target}) ({new_count})"
            result = result.replace(old_str, new_str)

    # Second pass: add counts to links that don't have them
    for match in LINK_WITHOUT_COUNT.finditer(result):
        link_text = match.group(1)
        link_target = match.group(2)

        file_path = memories_dir / link_target
        if not file_path.exists():
            continue

        count = get_memory_token_count(file_path)
        old_str = f"[{link_text}]({link_target})"
        new_str = f"[{link_text}]({link_target}) ({count})"
        result = result.replace(old_str, new_str, 1)

    return result


def update_memory_index(index_path: Path, memories_dir: Path) -> bool:
    """
    Update token counts in memory-index.md.

    Returns True if file was modified.
    """
    if not index_path.exists():
        print(f"Error: {index_path} not found", file=sys.stderr)
        sys.exit(1)

    original = index_path.read_text(encoding="utf-8")
    lines = original.split("\n")
    updated_lines = []

    for line in lines:
        if "[" in line and "](" in line and ".md)" in line:
            updated_lines.append(update_line(line, memories_dir))
        else:
            updated_lines.append(line)

    updated = "\n".join(updated_lines)

    if updated != original:
        index_path.write_text(updated, encoding="utf-8")
        return True

    return False


def main() -> int:
    if not HAS_TIKTOKEN:
        print("Warning: tiktoken not installed. Token counts not updated.", file=sys.stderr)
        print("  Install: pip install tiktoken", file=sys.stderr)
        return 2

    # Determine paths
    repo_root = Path(__file__).resolve().parent.parent
    memories_dir = repo_root / ".serena" / "memories"
    index_path = memories_dir / "memory-index.md"

    if not memories_dir.exists():
        print(f"Warning: {memories_dir} not found", file=sys.stderr)
        return 0

    if not index_path.exists():
        print(f"Warning: {index_path} not found", file=sys.stderr)
        return 0

    modified = update_memory_index(index_path, memories_dir)

    if modified:
        print("Updated token counts in memory-index.md")
    else:
        print("Token counts in memory-index.md already current")

    return 0


if __name__ == "__main__":
    sys.exit(main())
