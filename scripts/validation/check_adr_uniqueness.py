#!/usr/bin/env python3
"""Verify ADR numbers under `.agents/architecture/` are unique.

Per Issue #2253: concurrent ADR PRs each pick the same "next" number from
main at branch time. When the later PR merges, the earlier branches now
collide and must be manually renumbered. This script is the merge-time
gate that catches collisions deterministically and tells the author the
exact next free number to use.

Files are scanned by filename: `ADR-NNN-<slug>.md` in
`.agents/architecture/`. README and DESIGN-REVIEW prefixes are ignored.

The pre-existing duplicates tracked by Issue #2228 (ADR-058, ADR-062,
ADR-063) were resolved by renaming the non-canonical file in each pair to
the next free number (069, 070, 071). The allowlist is therefore empty: the
gate now enforces uniqueness with zero exceptions. Do NOT re-add numbers to
the allowlist for new collisions; renumber the incoming ADR instead.

Exit codes (per ADR-035):
    0 - all ADR numbers unique
    1 - one or more duplicates detected
    2 - config error (e.g. architecture directory missing)

Operator helpers:
    --print-next            print the next free ADR number and exit 0
    --print-next-padded N   same, zero-padded to N digits (default 3)
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

# ADR-NNN-<slug>.md. We accept 2+ digits to be forgiving but normalise to int.
ADR_FILENAME_RE = re.compile(r"^ADR-(\d{2,})-[^/]+\.md$")

# Issue #2228 deduplicated the formerly-colliding numbers (58/62/63), so the
# allowlist is now empty: the gate enforces uniqueness with zero exceptions.
# Do NOT re-add numbers here for new collisions; renumber the incoming ADR.
KNOWN_DUPLICATES_ISSUE_2228: frozenset[int] = frozenset()


def collect_adr_numbers(adr_dir: Path) -> dict[int, list[Path]]:
    """Return {adr_number: [paths]} for every ADR file under adr_dir."""
    by_number: dict[int, list[Path]] = defaultdict(list)
    for md in sorted(adr_dir.glob("ADR-*.md")):
        m = ADR_FILENAME_RE.match(md.name)
        if not m:
            # e.g. ADR-EXAMPLE.md or other non-numeric variants, skip.
            continue
        by_number[int(m.group(1))].append(md)
    return by_number


def find_new_duplicates(
    by_number: dict[int, list[Path]],
    allowlist: frozenset[int] = KNOWN_DUPLICATES_ISSUE_2228,
) -> list[tuple[int, list[Path]]]:
    """Return duplicates not covered by the #2228 allowlist."""
    return [
        (num, sorted(paths))
        for num, paths in sorted(by_number.items())
        if len(paths) > 1 and (num not in allowlist or len(paths) > 2)
    ]


def next_free_number(by_number: dict[int, list[Path]]) -> int:
    """Return max(existing) + 1. Empty repo yields 1."""
    return (max(by_number) + 1) if by_number else 1


def _format_dupes(dupes: list[tuple[int, list[Path]]], repo_root: Path) -> list[str]:
    lines = []
    for num, paths in dupes:
        rels = ", ".join(str(p.relative_to(repo_root)) for p in paths)
        lines.append(f"ADR-{num:03d}: {rels}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (defaults to two levels above this script).",
    )
    parser.add_argument(
        "--print-next",
        action="store_true",
        help="Print the next free ADR number and exit 0. Use as a "
        "one-shot helper before authoring a new ADR.",
    )
    parser.add_argument(
        "--print-next-padded",
        type=int,
        metavar="N",
        default=3,
        help="Zero-pad width for --print-next (default 3).",
    )
    args = parser.parse_args()

    adr_dir = args.repo_root / ".agents" / "architecture"
    if not adr_dir.is_dir():
        print(f"[CONFIG] ADR directory not found: {adr_dir}", file=sys.stderr)
        return 2

    by_number = collect_adr_numbers(adr_dir)

    if args.print_next:
        width = max(args.print_next_padded, 1)
        print(f"{next_free_number(by_number):0{width}d}")
        return 0

    new_dupes = find_new_duplicates(by_number)

    if new_dupes:
        print("[FAIL] Duplicate ADR numbers detected (see issue #2253):")
        for line in _format_dupes(new_dupes, args.repo_root):
            print(f"  - {line}")
        print(
            "\nTwo ADR PRs picked the same number off main. To fix the "
            "incoming PR, renumber its ADR to the next free value:"
        )
        print(f"\n  next free ADR number: {next_free_number(by_number):03d}")
        print(
            "\nRename the file, update the `# ADR-NNN:` heading, and sweep "
            "references with:\n"
            "  git grep -nE 'ADR-OLD\\b' .agents/ .claude/ src/ docs/\n\n"
            "Issue #2228 is already resolved: the incoming files that "
            "collided with canonical ADR-058, ADR-062, and ADR-063 were "
            "renumbered to ADR-069, ADR-070, and ADR-071. The allowlist is "
            "empty; do not add exceptions for new collisions."
        )
        return 1

    print(
        "[PASS] All ADR numbers in .agents/architecture/ unique "
        f"(next free: {next_free_number(by_number):03d})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
