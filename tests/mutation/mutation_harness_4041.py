"""Mutation harness for issue #4041 ratchet registry wiring.

Verifies that the taste and type-ignore registry entries are load-bearing.

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
_RATCHET_REL = Path("scripts/validation/checks_ratchet.py")
_TESTS = [
    "tests/ci/test_lefthook_ratchet_wiring.py",
    "tests/ci/test_pre_pr_runs_lefthook_ratchets.py",
]


def _run_tests(repo_root: Path) -> tuple[int, str]:
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
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return result.returncode, result.stdout + result.stderr


def _assert_suite_ran(return_code: int, output: str) -> None:
    if return_code == 4 or "no tests ran" in output.lower():
        raise RuntimeError(f"Mutation suite did not run:\n{output[-3000:]}")


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
    registry = repo_root / _RATCHET_REL
    original_bytes = registry.read_bytes()
    baseline_code, baseline_output = _run_tests(repo_root)
    _assert_suite_ran(baseline_code, baseline_output)
    if baseline_code != 0:
        raise RuntimeError(f"Unmutated suite is red:\n{baseline_output[-3000:]}")

    mutants = [
        (
            "remove taste-count-ratchet registry name",
            b'Ratchet("taste-count-ratchet",',
            b'Ratchet("XYZZY-DELETED-4041",',
        ),
        (
            "remove type-ignore-count-ratchet registry name",
            b'"type-ignore-count-ratchet",',
            b'"XYZZY-DELETED-4039",',
        ),
        (
            "remove taste-count-ratchet script",
            b'"scripts/ci/taste_count_ratchet.py"',
            b'"scripts/ci/MUTANT_DELETED.py"',
        ),
        (
            "remove type-ignore-count-ratchet script",
            b'"scripts/ci/type_ignore_count_ratchet.py"',
            b'"scripts/ci/MUTANT_DELETED_4039.py"',
        ),
    ]

    failures = []
    for name, old, new in mutants:
        print(f"\n--- Mutant: {name} ---")
        mutated = _apply_mutant(original_bytes, old, new)
        registry.write_bytes(mutated)
        try:
            rc, output = _run_tests(repo_root)
            _assert_suite_ran(rc, output)
            if rc == 0:
                failures.append(
                    f"SURVIVING MUTANT: '{name}' - tests passed when they should have failed"
                )
                print("  FAIL: tests did not detect the mutation")
            else:
                print(f"  PASS: tests caught the mutation (exit {rc})")
        finally:
            registry.write_bytes(original_bytes)
        restored = registry.read_bytes()
        assert restored == original_bytes, "Restore was not byte-identical!"

    inert = _apply_mutant(
        original_bytes,
        b"one authoritative registry",
        b"the authoritative registry",
    )
    registry.write_bytes(inert)
    try:
        inert_code, inert_output = _run_tests(repo_root)
        _assert_suite_ran(inert_code, inert_output)
        if inert_code != 0:
            failures.append("INVERTED CONTROL FAILED: inert mutation was rejected")
    finally:
        registry.write_bytes(original_bytes)

    if failures:
        print("\n\nSURVIVING MUTANTS DETECTED:")
        for msg in failures:
            print(f"  {msg}")
        sys.exit(1)
    else:
        print("\nAll mutants killed. Tests are load-bearing.")


def main() -> None:
    with isolated_mutation_worktree(_REPO_ROOT, [_RATCHET_REL]) as workspace:
        run_mutants(workspace.root)


if __name__ == "__main__":
    main()
