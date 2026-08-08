#!/usr/bin/env python3
"""
Repair or verify token counts in memory-index.md.

Reads memory-index.md, finds markdown links to memory files,
counts tokens for each referenced file, and renders the expected inline
token counts. Repair and check modes use the same rendering.

Exit codes per ADR-035:
  0 - Success (counts repaired or verified current)
  1 - Logic or input error (stale counts, missing file, count failure)
  2 - Configuration error (tiktoken not installed)
"""

import argparse
import re
import sys
from collections.abc import Sequence
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


def update_line(line: str, memories_dir: Path) -> tuple[str, int]:
    """Update token counts for all memory links in a single line."""
    result = line
    examined = 0

    # First pass: update existing counts
    for match in LINK_WITH_COUNT.finditer(line):
        link_text = match.group(1)
        link_target = match.group(2)
        old_count = int(match.group(3))

        file_path = memories_dir / link_target

        if not file_path.exists():
            raise FileNotFoundError(f"referenced memory not found: {file_path}")

        new_count = get_memory_token_count(file_path)
        examined += 1
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
            raise FileNotFoundError(f"referenced memory not found: {file_path}")

        count = get_memory_token_count(file_path)
        examined += 1
        old_str = f"[{link_text}]({link_target})"
        new_str = f"[{link_text}]({link_target}) ({count})"
        result = result.replace(old_str, new_str, 1)

    return result, examined


def render_memory_index(index_path: Path, memories_dir: Path) -> tuple[str, int]:
    """Return expected index content and the number of counted links."""
    original = index_path.read_text(encoding="utf-8")
    updated_lines: list[str] = []
    examined = 0

    for line in original.split("\n"):
        if "[" in line and "](" in line and ".md)" in line:
            updated_line, line_examined = update_line(line, memories_dir)
            updated_lines.append(updated_line)
            examined += line_examined
        else:
            updated_lines.append(line)

    return "\n".join(updated_lines), examined


def update_memory_index(index_path: Path, memories_dir: Path) -> bool:
    """Update token counts and return whether the file changed."""
    original = index_path.read_text(encoding="utf-8")
    updated, _examined = render_memory_index(index_path, memories_dir)

    if updated != original:
        index_path.write_text(updated, encoding="utf-8")
        return True

    return False


def check_memory_index(index_path: Path, memories_dir: Path) -> list[str]:
    """Return drifted token count descriptions without modifying the index."""
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
            actual = get_memory_token_count(file_path)
            if actual != recorded:
                drifted.append(
                    f"  {link_target}: recorded {recorded}, actual {actual}"
                )
    return drifted


def run(index_path: Path, memories_dir: Path, *, check: bool) -> int:
    """Repair or verify one memory index."""
    if not memories_dir.exists():
        print(f"Error: {memories_dir} not found", file=sys.stderr)
        return 1
    if not index_path.exists():
        print(f"Error: {index_path} not found", file=sys.stderr)
        return 1

    try:
        original = index_path.read_text(encoding="utf-8")
        expected, examined = render_memory_index(index_path, memories_dir)
    except (ImportError, OSError) as exc:
        print(f"Error: token count failed: {exc}", file=sys.stderr)
        return 1

    if examined == 0:
        print(f"Error: no memory links found in {index_path}", file=sys.stderr)
        return 1

    if check:
        if expected != original:
            print(
                f"Stale token counts in {index_path} "
                f"({examined} memory links examined)",
                file=sys.stderr,
            )
            return 1
        print(f"Token counts current ({examined} memory links examined)")
        return 0

    if expected != original:
        try:
            index_path.write_text(expected, encoding="utf-8")
        except OSError as exc:
            print(f"Error: failed to update {index_path}: {exc}", file=sys.stderr)
            return 1
        print(f"Updated token counts ({examined} memory links examined)")
    else:
        print(f"Token counts already current ({examined} memory links examined)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify counts without modifying memory-index.md.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    repo_root: Path | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if not HAS_TIKTOKEN:
        print("Error: tiktoken not installed. Token counts not checked.", file=sys.stderr)
        print("  Install: uv pip install tiktoken", file=sys.stderr)
        return 2

    root = repo_root or Path(__file__).resolve().parent.parent
    memories_dir = root / ".serena" / "memories"
    index_path = memories_dir / "memory-index.md"
    return run(index_path, memories_dir, check=args.check)


if __name__ == "__main__":
    sys.exit(main())
