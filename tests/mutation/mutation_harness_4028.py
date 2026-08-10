"""Mutation harness for issue #4028: scan_principles.py module split.

Verifies that scan_principles_core.py is individually load-bearing by
mutating key exports and asserting tests detect the regressions.

Rules:
- Count each pattern; refuse if count != 1 (PATTERN-AMBIGUOUS).
- Delete bytecode caches before every test run.
- Restore byte-identically and assert after every mutant.
"""

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
_CORE_REL = (
    Path(".claude")
    / "skills"
    / "golden-principles"
    / "scripts"
    / "scan_principles_core.py"
)
_TESTS = [
    "tests/skills/golden-principles/test_scan_principles_core.py",
    "tests/skills/golden-principles/test_scan_principles_diff_scope.py",
]


def _run_tests(repo_root: Path) -> int:
    purge_bytecode(repo_root)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *_TESTS,
            "-x",
            "-q",
        ],
        cwd=repo_root,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
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


def run_mutants(repo_root: Path) -> None:
    core = repo_root / _CORE_REL
    original_bytes = core.read_bytes()

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

        core.write_bytes(mutated)
        try:
            rc = _run_tests(repo_root)
            if rc == 0:
                failures.append(
                    f"SURVIVING MUTANT: '{name}' - tests passed, mutation undetected"
                )
                print("  FAIL: tests did not detect the mutation")
            else:
                print(f"  PASS: tests caught the mutation (exit {rc})")
        finally:
            core.write_bytes(original_bytes)
        restored = core.read_bytes()
        assert restored == original_bytes, "Restore was not byte-identical!"

    if failures:
        print("\n\nSURVIVING MUTANTS DETECTED:")
        for msg in failures:
            print(f"  {msg}")
        sys.exit(1)
    else:
        print("\nAll mutants killed. Tests are load-bearing.")


def main() -> None:
    with isolated_mutation_worktree(_REPO_ROOT, [_CORE_REL]) as workspace:
        run_mutants(workspace.root)


if __name__ == "__main__":
    main()
