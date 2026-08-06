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
  2 - Configuration error (tiktoken not installed, counts skipped)
"""

import argparse
import re
import sys
from pathlib import Path

# Graceful tiktoken import
try:
    _scripts = Path(__file__).resolve().parent.parent / ".claude/skills/memory/scripts"
    sys.path.insert(0, str(_scripts))
    from count_memory_tokens import _HAS_TIKTOKEN, get_memory_token_count
    HAS_TIKTOKEN = _HAS_TIKTOKEN
except ImportError:
    HAS_TIKTOKEN = False


LINK_WITH_COUNT = re.compile(
    r'\[([^\]]+)\]\(([^)]+\.md)\)\s*\((\d+)\)'
)
LINK_WITHOUT_COUNT = re.compile(
    r'\[([^\]]+)\]\(([^)]+\.md)\)(?!\s*\(\d+\))'
)
MEMORY_LINK_TARGET = re.compile(
    r'\[[^\]]+\]\(([^)]+\.md)\)(?:\s*\(\d+\))?'
)


class DuplicateMemoryIndexEntryError(ValueError):
    """Raised when duplicate memory-index rows cannot be healed safely."""


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

        try:
            new_count = get_memory_token_count(file_path)
        except (ImportError, OSError) as e:
            print(f"Warning: Failed to count {file_path}: {e}", file=sys.stderr)
            continue
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

        try:
            count = get_memory_token_count(file_path)
        except (ImportError, OSError) as e:
            print(f"Warning: Failed to count {file_path}: {e}", file=sys.stderr)
            continue
        old_str = f"[{link_text}]({link_target})"
        new_str = f"[{link_text}]({link_target}) ({count})"
        result = result.replace(old_str, new_str, 1)

    return result


def _memory_link_targets(line: str) -> list[str]:
    return [match.group(1) for match in MEMORY_LINK_TARGET.finditer(line)]


def collapse_duplicate_rows(lines: list[str]) -> tuple[list[str], bool]:
    """Collapse union-merged duplicate rows after token counts match."""
    kept_lines: list[str] = []
    seen_memory_rows: set[str] = set()
    changed = False

    for line_number, line in enumerate(lines, start=1):
        targets = _memory_link_targets(line)
        unique_targets = sorted(set(targets))
        if not unique_targets:
            kept_lines.append(line)
            continue

        if len(targets) != len(unique_targets):
            repeated = sorted({
                target for target in unique_targets if targets.count(target) > 1
            })
            raise DuplicateMemoryIndexEntryError(
                f"Line {line_number} repeats memory link(s): {', '.join(repeated)}"
            )

        if line in seen_memory_rows:
            changed = True
            continue

        kept_lines.append(line)
        seen_memory_rows.add(line)

    return kept_lines, changed


def check_memory_index(index_path: Path, memories_dir: Path) -> list[str]:
    """Return lines describing drifted token counts without modifying the file.

    Each entry in the returned list describes one row where the recorded count
    differs from the computed count. An empty list means all counts are current.
    This is the ``--check`` mode counterpart to ``update_memory_index``
    (issue #4441).
    """
    if not index_path.exists():
        print(f"Error: {index_path} not found", file=sys.stderr)
        sys.exit(1)

    drifted: list[str] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if "[" not in line or "](" not in line or ".md)" not in line:
            continue
        for match in LINK_WITH_COUNT.finditer(line):
            link_target = match.group(2)
            recorded = int(match.group(3))
            file_path = memories_dir / link_target
            if not file_path.exists():
                continue
            try:
                actual = get_memory_token_count(file_path)
            except (ImportError, OSError):
                continue
            if actual != recorded:
                drifted.append(
                    f"  {link_target}: recorded {recorded}, actual {actual}"
                )
    return drifted


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

    collapsed_lines, collapsed = collapse_duplicate_rows(updated_lines)
    updated = "\n".join(collapsed_lines)

    if updated != original:
        index_path.write_text(updated, encoding="utf-8")
        return True

    return collapsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Update or check token counts in memory-index.md."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Check mode: exit non-zero if any recorded count differs from the "
            "computed count, printing drifted entries. Does not modify the file."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args([] if argv is None else argv)

    if not HAS_TIKTOKEN:
        print("Warning: tiktoken not installed. Token counts not updated.", file=sys.stderr)
        print("  Install: uv pip install tiktoken", file=sys.stderr)
        return 2

    # Determine paths
    repo_root = Path(__file__).resolve().parent.parent
    memories_dir = repo_root / ".serena" / "memories"
    index_path = memories_dir / "memory-index.md"

    if not memories_dir.exists():
        print(f"Error: {memories_dir} not found", file=sys.stderr)
        return 1

    if not index_path.exists():
        print(f"Error: {index_path} not found", file=sys.stderr)
        return 1

    if args.check:
        drifted = check_memory_index(index_path, memories_dir)
        if drifted:
            print("memory-index.md token counts are stale:")
            for line in drifted:
                print(line)
            print(
                "Run `uv run python scripts/update_memory_index_tokens.py` to fix."
            )
            return 1
        print("memory-index.md token counts are current")
        return 0

    try:
        modified = update_memory_index(index_path, memories_dir)
    except DuplicateMemoryIndexEntryError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if modified:
        print("Updated token counts in memory-index.md")
    else:
        print("Token counts in memory-index.md already current")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
