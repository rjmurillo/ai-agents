"""Mutation harness for issue #4028: scan_principles.py module split.

Verifies that scan_principles_core.py is individually load-bearing by
mutating key exports and asserting tests detect the regressions.

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
_CORE = (
    _REPO_ROOT
    / ".claude"
    / "skills"
    / "golden-principles"
    / "scripts"
    / "scan_principles_core.py"
)
_TESTS = [
    "tests/skills/golden-principles/test_scan_principles_core.py",
    "tests/skills/golden-principles/test_scan_principles_diff_scope.py",
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
    original_bytes = _CORE.read_bytes()

    mutants = [
        (
            "break Violation dataclass name",
            b"class Violation:",
            b"class MUTANT_Violation_DELETED:",
        ),
        (
            "break ScanResult dataclass name",
            b"class ScanResult:",
            b"class MUTANT_ScanResult_DELETED:",
        ),
        (
            "break get_diff_files function signature",
            b"def get_diff_files(",
            b"def MUTANT_get_diff_files_DELETED(",
        ),
        (
            "break _git_root function signature",
            b"def _git_root() -> str:",
            b"def MUTANT_git_root_DELETED() -> str:",
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

        _CORE.write_bytes(mutated)
        time.sleep(1.1)

        rc = _run_tests()
        if rc == 0:
            failures.append(f"SURVIVING MUTANT: '{name}' - tests passed when they should have failed")
            print("  FAIL: tests did not detect the mutation")
        else:
            print(f"  PASS: tests caught the mutation (exit {rc})")

        _CORE.write_bytes(original_bytes)
        time.sleep(1.1)
        restored = _CORE.read_bytes()
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
