"""Mutation harness for issue #4039: type-ignore count ratchet.

Verifies that the new type_ignore_count_ratchet.py is individually
load-bearing by mutating core patterns and asserting tests detect them.

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
_RATCHET = _REPO_ROOT / "scripts" / "ci" / "type_ignore_count_ratchet.py"
_TESTS = [
    "tests/ci/test_type_ignore_count_ratchet.py",
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
    original_bytes = _RATCHET.read_bytes()

    mutants = [
        (
            "break type-ignore regex to never match",
            b'_TYPE_IGNORE_RE = re.compile(r"#\\s*type:\\s*ignore(?:\\[[^\\]]*\\])?")' ,
            b'_TYPE_IGNORE_RE = re.compile(r"MUTANT_WILL_NEVER_MATCH_XYZZY")',
        ),
        (
            "break PY_GLOBS to use wrong extension",
            b'_PY_GLOBS = ("*.py",)',
            b'_PY_GLOBS = ("*.MUTANT_EXTENSION",)',
        ),
        (
            "break baseline filename reference",
            b'_BASELINE_PATH = Path(__file__).with_name("type_ignore_count_baseline.txt")',
            b'_BASELINE_PATH = Path(__file__).with_name("MUTANT_type_ignore_count_baseline.txt")',
        ),
    ]

    failures = []
    for name, old, new in mutants:
        print(f"\n--- Mutant: {name} ---")
        try:
            mutated = _apply_mutant(original_bytes, old, new)
        except ValueError as exc:
            print(f"  SKIP: {exc}")
            continue

        _RATCHET.write_bytes(mutated)
        time.sleep(1.1)

        rc = _run_tests()
        if rc == 0:
            failures.append(f"SURVIVING MUTANT: '{name}' - tests passed, mutation undetected")
            print("  FAIL: tests did not detect the mutation")
        else:
            print(f"  PASS: tests caught the mutation (exit {rc})")

        _RATCHET.write_bytes(original_bytes)
        time.sleep(1.1)
        restored = _RATCHET.read_bytes()
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
