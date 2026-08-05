#!/usr/bin/env python3
"""Fail when ``.serena/memories/memory-index.md`` records a stale token count.

``scripts/update_memory_index_tokens.py`` repairs the counts, and lefthook runs
it at ``pre-commit`` as the ``memory-token-update`` autofix. This verifier imports
the repair script's own count and coverage functions so repair and verification
cannot drift apart. Issue #4441 reported the token-count symptom. Issue #4313
reported the matching coverage symptom: a memory file missing from the root
index was invisible to retrieval, and every gate still exited zero.

Measured on pristine ``main`` at 3dbf3a381a: running the repair rewrote two
lines, because ``skills-git-index.md`` recorded ``(287)`` against an actual
``324``. An autofix with no verifier is not a gate; it is a suggestion.

This is two ratchets. Token-count drift has a fixed baseline of zero. Unindexed
memory files have a measured backlog baseline of 839 on clean ``origin/main`` at
95ecfc3e9c, so the gate fails only when that count increases. That avoids
blocking every push while still preventing new invisible memories.

Exit codes per ADR-035:
  0 - Every recorded count matches the file it points at
  1 - At least one count is stale (each one is named)
  2 - Cannot verify (tiktoken missing, or the index is absent)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from update_memory_index_tokens import (  # noqa: E402
    HAS_TIKTOKEN,
    UNINDEXED_MEMORY_BASELINE,
    coverage_errors,
    index_coverage,
    print_coverage_errors,
    update_line,
)


def drifted_lines(index_text: str, memories_dir: Path) -> list[tuple[int, str, str]]:
    """Return ``(line_number, recorded, expected)`` for every stale index line.

    Reuses the repair's own ``update_line`` rather than reimplementing the
    count. A verifier that computes the expected value differently from the
    repair can disagree with it, and then the two fight: the gate fails, the
    contributor runs the repair, and the gate fails again on the repaired file.
    """
    drifted: list[tuple[int, str, str]] = []
    for number, line in enumerate(index_text.split("\n"), start=1):
        if "[" not in line or "](" not in line or ".md)" not in line:
            continue
        expected = update_line(line, memories_dir)
        if expected != line:
            drifted.append((number, line.strip(), expected.strip()))
    return drifted


def main(argv: list[str] | None = None) -> int:
    """Check the index and report every stale entry by name."""
    del argv  # No options: a fixed floor of zero has nothing to configure.

    if not HAS_TIKTOKEN:
        print(
            "ERROR: tiktoken is not importable, so token counts cannot be "
            "verified. tiktoken is a locked project dependency, so this is a "
            "broken environment rather than a routine skip. Reporting 'cannot "
            "verify' instead of a pass, because a gate that goes green when it "
            "checked nothing is worse than no gate.",
            file=sys.stderr,
        )
        return 2

    memories_dir = _REPO_ROOT / ".serena" / "memories"
    index_path = memories_dir / "memory-index.md"
    if not index_path.is_file():
        print(f"ERROR: memory index not found: {index_path}", file=sys.stderr)
        return 2

    drifted = drifted_lines(index_path.read_text(encoding="utf-8"), memories_dir)
    coverage = index_coverage(index_path, memories_dir)
    coverage_failures = coverage_errors(coverage, UNINDEXED_MEMORY_BASELINE)

    if not drifted and not coverage_failures:
        print(
            "memory-index.md token counts are current; "
            f"{len(coverage.unindexed_files)} unindexed file(s) <= baseline "
            f"{UNINDEXED_MEMORY_BASELINE}; "
            f"{len(coverage.stale_index_references)} stale reference(s)"
        )
        return 0

    if drifted:
        print(
            f"ERROR: {len(drifted)} memory-index.md token count(s) are stale. "
            "A stale count misroutes retrieval: a reader budgeting context "
            "trusts the recorded number, and (0) reads as 'this memory is "
            "empty, skip it'.",
            file=sys.stderr,
        )
        for number, recorded, expected in drifted:
            print(f"  line {number}:", file=sys.stderr)
            print(f"    recorded: {recorded}", file=sys.stderr)
            print(f"    actual:   {expected}", file=sys.stderr)

    if coverage_failures:
        print_coverage_errors(coverage, UNINDEXED_MEMORY_BASELINE)

    print(
        "\nFix: uv run --frozen python scripts/update_memory_index_tokens.py",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
