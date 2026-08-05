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

import re
import sys
from dataclasses import dataclass
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
INDEX_LINK_TARGET = re.compile(r'\[[^\]]+\]\(([^)]+\.md)\)')
SPECIAL_MEMORY_FILENAMES = frozenset({
    "CLAUDE.md",
    "README.md",
    "memory-index.md",
})
UNINDEXED_MEMORY_BASELINE = 839
REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class MemoryIndexCoverage:
    """Coverage of memory files by the root memory index."""

    memory_files: tuple[str, ...]
    index_references: tuple[str, ...]
    unindexed_files: tuple[str, ...]
    stale_index_references: tuple[str, ...]

    @property
    def memory_file_count(self) -> int:
        """Return the number of memory files that should be indexed."""
        return len(self.memory_files)

    @property
    def index_reference_count(self) -> int:
        """Return the number of file references in memory-index.md."""
        return len(self.index_references)


def collect_memory_files(memories_dir: Path) -> tuple[str, ...]:
    """Return memory files that should have a root index row."""
    files = {
        path.relative_to(memories_dir).as_posix()
        for path in memories_dir.rglob("*.md")
        if path.name not in SPECIAL_MEMORY_FILENAMES
    }
    return tuple(sorted(files))


def collect_index_references(index_text: str) -> tuple[str, ...]:
    """Return markdown link targets recorded in memory-index.md."""
    references = {
        match.group(1)
        for match in INDEX_LINK_TARGET.finditer(index_text)
    }
    return tuple(sorted(references))


def index_coverage(index_path: Path, memories_dir: Path) -> MemoryIndexCoverage:
    """Compare memory files to the root memory index references."""
    memory_files = collect_memory_files(memories_dir)
    index_references = collect_index_references(
        index_path.read_text(encoding="utf-8")
    )
    memory_file_set = set(memory_files)
    index_reference_set = set(index_references)

    return MemoryIndexCoverage(
        memory_files=memory_files,
        index_references=index_references,
        unindexed_files=tuple(sorted(memory_file_set - index_reference_set)),
        stale_index_references=tuple(sorted(index_reference_set - memory_file_set)),
    )


def coverage_errors(
    coverage: MemoryIndexCoverage,
    unindexed_baseline: int = UNINDEXED_MEMORY_BASELINE,
) -> list[str]:
    """Return fail-closed coverage errors for the root index."""
    errors: list[str] = []
    if coverage.stale_index_references:
        errors.append(
            f"{len(coverage.stale_index_references)} stale "
            "memory-index reference(s)"
        )
    if len(coverage.unindexed_files) > unindexed_baseline:
        errors.append(
            "unindexed memory file count increased: "
            f"{len(coverage.unindexed_files)} > {unindexed_baseline}"
        )
    return errors


def print_coverage_errors(
    coverage: MemoryIndexCoverage,
    unindexed_baseline: int = UNINDEXED_MEMORY_BASELINE,
) -> None:
    """Print actionable coverage errors to stderr."""
    for error in coverage_errors(coverage, unindexed_baseline):
        print(f"ERROR: {error}", file=sys.stderr)

    if coverage.stale_index_references:
        print("Stale memory-index reference(s):", file=sys.stderr)
        for reference in coverage.stale_index_references[:20]:
            print(f"  {reference}", file=sys.stderr)
        if len(coverage.stale_index_references) > 20:
            remaining = len(coverage.stale_index_references) - 20
            print(f"  ... {remaining} more", file=sys.stderr)

    if len(coverage.unindexed_files) > unindexed_baseline:
        print(
            "Unindexed memory file(s) above the measured baseline:",
            file=sys.stderr,
        )
        for file_name in coverage.unindexed_files[:20]:
            print(f"  {file_name}", file=sys.stderr)
        if len(coverage.unindexed_files) > 20:
            remaining = len(coverage.unindexed_files) - 20
            print(f"  ... {remaining} more", file=sys.stderr)
        print(
            "Add keyword rows to .serena/memories/memory-index.md, then run "
            "uv run --frozen python scripts/update_memory_index_tokens.py",
            file=sys.stderr,
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


def run(repo_root: Path) -> int:
    """Update token counts and verify root index coverage for repo_root."""
    if not HAS_TIKTOKEN:
        print(
            "Warning: tiktoken not installed. Token counts not updated.",
            file=sys.stderr,
        )
        print("  Install: uv pip install tiktoken", file=sys.stderr)
        return 2

    memories_dir = repo_root / ".serena" / "memories"
    index_path = memories_dir / "memory-index.md"

    if not memories_dir.exists():
        print(f"Error: {memories_dir} not found", file=sys.stderr)
        return 1

    if not index_path.exists():
        print(f"Error: {index_path} not found", file=sys.stderr)
        return 1

    modified = update_memory_index(index_path, memories_dir)
    coverage = index_coverage(index_path, memories_dir)

    if modified:
        print("Updated token counts in memory-index.md")
    else:
        print("Token counts in memory-index.md already current")

    errors = coverage_errors(coverage, UNINDEXED_MEMORY_BASELINE)
    if errors:
        print_coverage_errors(coverage, UNINDEXED_MEMORY_BASELINE)
        return 1

    print(
        "Memory index coverage verified: "
        f"{len(coverage.unindexed_files)} unindexed file(s) <= baseline "
        f"{UNINDEXED_MEMORY_BASELINE}; "
        f"{len(coverage.stale_index_references)} stale reference(s)"
    )
    return 0


def main() -> int:
    return run(REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
