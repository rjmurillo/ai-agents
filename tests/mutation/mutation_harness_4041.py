"""Mutation harness for issue #4041: taste-count-ratchet pre-push wiring.

Verifies that each added lefthook.yml entry is individually load-bearing
by mutating it and asserting the wiring tests detect the regression.

Rules:
- Count each pattern; refuse if count != 1 (PATTERN-AMBIGUOUS).
- sleep(1.1) after every file write to defeat 1-second bytecode mtime cache.
- Restore byte-identically and assert after every mutant.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"
_TESTS = [
    "tests/ci/test_lefthook_ratchet_wiring.py",
]


def _run_tests() -> int:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *_TESTS,
            "-x",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
    )
    return result.returncode


def _apply_mutant(original: bytes, old: bytes, new: bytes) -> bytes:
    count = original.count(old)
    if count == 0:
        raise ValueError(f"PATTERN-AMBIGUOUS: pattern not found: {old!r}")
    if count > 1:
        raise ValueError(
            f"PATTERN-AMBIGUOUS: pattern appears {count} times (need exactly 1): {old!r}"
        )
    return original.replace(old, new, 1)


def run_mutants() -> None:
    original_bytes = _LEFTHOOK.read_bytes()

    mutants = [
        (
            "remove taste-count-ratchet job name",
            b"          - name: taste-count-ratchet",
            b"          - name: XYZZY-DELETED-4041",
        ),
        (
            "remove type-ignore-count-ratchet job name",
            b"          - name: type-ignore-count-ratchet",
            b"          - name: XYZZY-DELETED-4039",
        ),
        (
            "remove taste-count-ratchet run command",
            # Pattern includes leading spaces to match exactly one occurrence; noqa: E501
            b"            run: uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref origin/main",  # noqa: E501
            b"            run: echo MUTANT-DELETED",
        ),
        (
            "remove type-ignore-count-ratchet run command",
            # Pattern includes leading spaces to match exactly one occurrence; noqa: E501
            b"            run: uv run --frozen python scripts/ci/type_ignore_count_ratchet.py --base-ref origin/main",  # noqa: E501
            b"            run: echo MUTANT-DELETED-4039",
        ),
    ]

    failures = []
    for name, old, new in mutants:
        print(f"\n--- Mutant: {name} ---")
        mutated = _apply_mutant(original_bytes, old, new)
        _LEFTHOOK.write_bytes(mutated)
        time.sleep(1.1)

        rc = _run_tests()
        if rc == 0:
            failures.append(
                f"SURVIVING MUTANT: '{name}' - tests passed when they should have failed"
            )
            print("  FAIL: tests did not detect the mutation")
        else:
            print(f"  PASS: tests caught the mutation (exit {rc})")

        _LEFTHOOK.write_bytes(original_bytes)
        time.sleep(1.1)
        restored = _LEFTHOOK.read_bytes()
        assert restored == original_bytes, "Restore was not byte-identical!"

    if failures:
        print("\n\nSURVIVING MUTANTS DETECTED:")
        for msg in failures:
            print(f"  {msg}")
        sys.exit(1)
    else:
        print("\nAll mutants killed. Tests are load-bearing.")


if __name__ == "__main__":
    run_mutants()
