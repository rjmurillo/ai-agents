#!/usr/bin/env python3
"""Mutation harness for migrate_causal_version.py.

Three outcomes per mutant:
  DEAD         - at least one test failed (mutation caught)
  SURVIVED     - all tests passed (mutation not caught; test is wrong)
  DID-NOT-APPLY - the target literal was absent; file was byte-identical after
                  the substitution. Exits nonzero when this happens.

Usage: uv run --frozen python tests/skills/memory/mutate_migrate_causal_version.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "memory"
    / "scripts"
    / "migrate_causal_version.py"
)
_TEST = Path(__file__).resolve().parent / "test_migrate_causal_version.py"

_MUTATIONS: list[tuple[str, str, str, int]] = [
    # (name, find, replace, occurrence)
    (
        "BREAK_dry_run_version_check",
        'data.get("causal_order_version") == _CAUSAL_ORDER_VERSION:',
        'data.get("causal_order_version") != _CAUSAL_ORDER_VERSION:',
        1,
    ),
    (
        "BREAK_migrate_version_check",
        'data.get("causal_order_version") == _CAUSAL_ORDER_VERSION:',
        'data.get("causal_order_version") != _CAUSAL_ORDER_VERSION:',
        2,
    ),
    (
        "BREAK_topology_match",
        "if _edge_set(rebuilt) == orig_edges:",
        "if _edge_set(rebuilt) != orig_edges:",
        1,
    ),
    (
        "BREAK_edge_drop_guard",
        "if rebuilt_count < orig_count:",
        "if rebuilt_count > orig_count:",
        1,
    ),
    (
        "BREAK_skip_exit_code",
        "return 1 if any(counts.get(outcome, 0) > 0 for outcome in _FAILURE_OUTCOMES) else 0",
        "return 0 if any(counts.get(outcome, 0) > 0 for outcome in _FAILURE_OUTCOMES) else 0",
        1,
    ),
]


def run_tests() -> bool:
    """Return True when all tests pass."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(_TEST),
            "-q",
            "--tb=no",
            "--no-header",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.returncode == 0


def apply(original: str, find: str, replace: str, occurrence: int) -> tuple[str, bool]:
    """Return (mutated_text, applied). applied is False when find is absent."""
    if occurrence < 1:
        return original, False
    start = -1
    search_from = 0
    for _ in range(occurrence):
        start = original.find(find, search_from)
        if start == -1:
            return original, False
        search_from = start + len(find)
    if start == -1:
        return original, False
    return original[:start] + replace + original[start + len(find) :], True


def main() -> int:
    backup = _SCRIPT.read_text(encoding="utf-8")

    results: list[tuple[str, str]] = []
    did_not_apply: list[str] = []

    for name, find, replace, occurrence in _MUTATIONS:
        original = _SCRIPT.read_text(encoding="utf-8")
        mutated, applied = apply(original, find, replace, occurrence)

        if not applied:
            # File would be byte-identical; the literal is missing.
            results.append((name, "DID-NOT-APPLY"))
            did_not_apply.append(name)
            continue

        _SCRIPT.write_text(mutated, encoding="utf-8")
        try:
            passed = run_tests()
        finally:
            _SCRIPT.write_text(backup, encoding="utf-8")

        outcome = "SURVIVED" if passed else "DEAD"
        results.append((name, outcome))

    print()
    print("=== Mutation results ===")
    for name, outcome in results:
        print(f"  {outcome:<16} {name}")
    print()

    survived = [n for n, o in results if o == "SURVIVED"]
    dna = [n for n, o in results if o == "DID-NOT-APPLY"]

    if survived:
        print(f"FAILED: {len(survived)} mutant(s) survived", file=sys.stderr)
        for n in survived:
            print(f"  SURVIVED: {n}", file=sys.stderr)

    if dna:
        print(f"FAILED: {len(dna)} mutant(s) DID-NOT-APPLY (literal absent)", file=sys.stderr)
        for n in dna:
            print(f"  DID-NOT-APPLY: {n}", file=sys.stderr)

    if survived or dna:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
