"""Mutation harness for issue #3936: context-optimizer classifier logic.

Issue #3936 removed the inverted always_needed heuristic from
analyze_skill_placement.py. The fix landed in origin/main via #4234
(dropped detect_always_needed_patterns and removed the always_needed
parameter from get_classification). This harness verifies that the
current classification logic -- based on reference_ratio and tool-call
counts -- is individually load-bearing.

Rules:
- Count each pattern; exit nonzero with DID-NOT-APPLY when count != 1.
- cmp -s check: fail if mutated bytes are identical to original (no mutation applied).
- Delete bytecode caches before every test run.
- Restore byte-identically and assert after every mutant.
- Outcomes: DEAD (tests caught it), SURVIVED (tests missed it), DID-NOT-APPLY (pattern absent).
"""
# taste-lint: ignore file-size
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from scripts.testing.mutation_workspace import (
    isolated_mutation_worktree,
    purge_bytecode,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TARGET_REL = (
    Path(".claude")
    / "skills"
    / "context-optimizer"
    / "scripts"
    / "analyze_skill_placement.py"
)
_TESTS = [
    "tests/context-optimizer/test_analyze_skill_placement.py",
    "tests/context-optimizer/test_analyze_skill_placement_classification.py",
]


def _run_tests(repo_root: Path) -> int:
    purge_bytecode(repo_root)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *_TESTS, "-x", "-q"],
        cwd=repo_root,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return result.returncode


def _apply_mutant(original: bytes, old: bytes, new: bytes) -> tuple[bytes, str]:
    """Return mutated bytes and a status string."""
    count = original.count(old)
    if count == 0:
        return original, "DID-NOT-APPLY"
    if count > 1:
        raise ValueError(
            f"PATTERN-AMBIGUOUS: pattern appears {count} times (need exactly 1): {old!r}"
        )
    mutated = original.replace(old, new, 1)
    if mutated == original:
        raise ValueError(f"Mutation produced byte-identical output for: {old!r}")
    return mutated, "OK"


def run_mutants(repo_root: Path) -> None:
    target = repo_root / _TARGET_REL
    original_bytes = target.read_bytes()

    mutants = [
        (
            "weaken reference_ratio threshold from 0.7 to 0.99 (blocks PassiveContext)",
            b"    if reference_ratio > 0.7:",
            b"    if reference_ratio > 0.99:  # MUTANT-DELETED-3936",
        ),
        (
            "zero out passive_score addition for high reference_ratio",
            b"        score.passive_score += 3",
            b"        score.passive_score += 0  # MUTANT-DELETED-3936",
        ),
        (
            "weaken tool_calls threshold from 5 to 999 (blocks Skill)",
            b"    if tool_calls > 5:",
            b"    if tool_calls > 999:  # MUTANT-DELETED-3936",
        ),
        (
            "zero out skill_score addition for high tool_calls",
            b"        score.skill_score += 3",
            b"        score.skill_score += 0  # MUTANT-DELETED-3936",
        ),
    ]

    dead: list[str] = []
    survived: list[str] = []
    did_not_apply: list[str] = []

    for name, old, new in mutants:
        print(f"\n--- Mutant: {name} ---")
        mutated, status = _apply_mutant(original_bytes, old, new)

        if status == "DID-NOT-APPLY":
            did_not_apply.append(name)
            print("  DID-NOT-APPLY: pattern not found in target file")
            continue

        target.write_bytes(mutated)
        on_disk = target.read_bytes()
        if on_disk == original_bytes:
            target.write_bytes(original_bytes)
            did_not_apply.append(name)
            print("  DID-NOT-APPLY: file byte-identical after write")
            continue

        try:
            rc = _run_tests(repo_root)
            if rc == 0:
                survived.append(name)
                print("  SURVIVED: tests passed when they should have failed")
            else:
                dead.append(name)
                print(f"  DEAD: tests caught the mutation (exit {rc})")
        finally:
            target.write_bytes(original_bytes)
        restored = target.read_bytes()
        assert restored == original_bytes, f"Restore was not byte-identical for: {name}"

    print(f"\n{'='*60}")
    print(f"DEAD:          {len(dead)}")
    print(f"SURVIVED:      {len(survived)}")
    print(f"DID-NOT-APPLY: {len(did_not_apply)}")

    if did_not_apply:
        print("\nDID-NOT-APPLY (patterns not found -- verify target still contains them):")
        for msg in did_not_apply:
            print(f"  {msg}")

    if survived:
        print("\nSURVIVING MUTANTS (test suite did not detect):")
        for msg in survived:
            print(f"  {msg}")
        sys.exit(1)

    if did_not_apply:
        print("\nDID-NOT-APPLY mutations present -- target may have changed.")
        sys.exit(2)

    print("\nAll mutants killed. Tests are load-bearing.")


def main() -> None:
    with isolated_mutation_worktree(_REPO_ROOT, [_TARGET_REL]) as workspace:
        run_mutants(workspace.root)


if __name__ == "__main__":
    main()
