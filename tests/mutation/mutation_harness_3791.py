"""Mutation harness for issue #3791: check_python3_entrypoints validator.

Verifies that each load-bearing component of check_python3_entrypoints.py
is individually detectable by the test suite.

Rules:
- Count each pattern; exit nonzero with DID-NOT-APPLY when count != 1.
- cmp -s check: fail if mutated bytes are identical to original (no mutation applied).
- Delete bytecode caches before every test run.
- Restore byte-identically and assert after every mutant.
- Outcomes: DEAD (tests caught it), SURVIVED (tests missed it), DID-NOT-APPLY (pattern absent).
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
_TARGET_REL = Path("scripts") / "validation" / "check_python3_entrypoints.py"
_TESTS = [
    "tests/test_check_python3_entrypoints.py",
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
    """Return mutated bytes and a status string.

    Returns (mutated_bytes, "OK") on success.
    Returns (original, "DID-NOT-APPLY") if pattern is absent.
    Raises ValueError if pattern appears more than once.
    """
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
            "remove _BARE_PY3_PATTERN regex",
            b'_BARE_PY3_PATTERN = re.compile(r"(?<!\\w)python3\\s+(scripts/[^\\s`\\"\']+\\.py)")',
            b'_BARE_PY3_PATTERN = re.compile(r"MUTANT-DELETED-3791-NEVER-MATCHES")',
        ),
        (
            "remove yaml from _THIRD_PARTY_IMPORTS",
            b'        "yaml",  # PyYAML',
            b'        # "yaml",  # MUTANT-DELETED-3791',
        ),
        (
            "suppress violation return in check_docs",
            b"                if bad:\n                    violations.append((doc_path, lineno, rel, bad))",  # noqa: E501
            b"                if bad:\n                    pass  # MUTANT-DELETED-3791",
        ),
        (
            "change exit-1 return to exit-0 in main",
            b"    return 1\n\n\nif __name__ == \"__main__\":",
            b"    return 0  # MUTANT-DELETED-3791\n\n\nif __name__ == \"__main__\":",
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
