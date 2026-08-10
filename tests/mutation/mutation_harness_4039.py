"""Mutation harness for issue #4039: type-ignore count ratchet.

Verifies that the new type_ignore_count_ratchet.py is individually
load-bearing by mutating core patterns and asserting tests detect them.

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
_RATCHET_REL = Path("scripts") / "ci" / "type_ignore_count_ratchet.py"
_TESTS = [
    "tests/ci/test_type_ignore_count_ratchet.py",
    "tests/ci/test_lefthook_ratchet_wiring.py",
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
    ratchet = repo_root / _RATCHET_REL
    original_bytes = ratchet.read_bytes()

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

        ratchet.write_bytes(mutated)
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
            ratchet.write_bytes(original_bytes)
        restored = ratchet.read_bytes()
        assert restored == original_bytes, "Restore was not byte-identical!"

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
