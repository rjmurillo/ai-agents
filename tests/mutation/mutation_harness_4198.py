"""Mutation harness for issues #4198/#4195: prose portability CI wiring.

Verifies that each new structural property added to validate-vendor-portability.yml
is individually load-bearing by mutating the file and asserting the wiring tests
detect the regression.

Rules:
- Count each pattern; report DID-NOT-APPLY when count != 1.
- cmp byte-identical after mutation to confirm the patch actually changed the file.
- sleep(1.1) after every file write to defeat 1-second bytecode mtime cache.
- Assert byte-identical restore after every mutant.
- Three outcomes: DEAD (test caught it), SURVIVED (test missed it), DID-NOT-APPLY (pattern absent).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT / ".github" / "workflows" / "validate-vendor-portability.yml"
)
_TESTS = [
    "tests/ci/test_validate_vendor_portability_wiring.py",
]

_MUTANTS: list[tuple[str, bytes, bytes]] = [
    (
        "remove prose portability step from validate-portability job",
        (
            b"\n      - name: Check skill prose portability ratchet"
            b"\n        run: python3 scripts/validation/check_skill_md_portability.py"
        ),
        b"",
    ),
    (
        "remove check_skill_md_portability.py from paths-filter",
        b"\n              - 'scripts/validation/check_skill_md_portability.py'",
        b"",
    ),
    (
        "remove skill_md_portability_baseline.json from paths-filter",
        b"\n              - 'scripts/validation/skill_md_portability_baseline.json'",
        b"",
    ),
    (
        "replace run command with wrong script",
        b"        run: python3 scripts/validation/check_skill_md_portability.py\n",
        b"        run: python3 scripts/validation/XYZZY_WRONG_SCRIPT.py\n",
    ),
]


def _run_tests() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *_TESTS, "-x", "-q"],
        cwd=_REPO_ROOT,
        capture_output=True,
    )
    return result.returncode


def _apply_mutant(original: bytes, old: bytes, new: bytes) -> tuple[str, bytes]:
    """Return (outcome, mutated_bytes).

    outcome is one of "ok", "DID-NOT-APPLY", "PATTERN-AMBIGUOUS (N)".
    """
    count = original.count(old)
    if count == 0:
        return ("DID-NOT-APPLY", original)
    if count > 1:
        return (f"PATTERN-AMBIGUOUS ({count} occurrences)", original)
    return ("ok", original.replace(old, new, 1))


def _run_one_mutant(
    name: str,
    old: bytes,
    new: bytes,
    original_bytes: bytes,
) -> str:
    """Apply one mutant, run tests, restore. Return outcome string."""
    outcome, mutated_bytes = _apply_mutant(original_bytes, old, new)
    if outcome != "ok":
        print(f"  {outcome}")
        return outcome

    if mutated_bytes == original_bytes:
        print("  DID-NOT-APPLY: file unchanged after patch")
        return "DID-NOT-APPLY"

    _WORKFLOW.write_bytes(mutated_bytes)
    time.sleep(1.1)
    rc = _run_tests()
    _WORKFLOW.write_bytes(original_bytes)
    time.sleep(1.1)
    restored = _WORKFLOW.read_bytes()
    assert restored == original_bytes, f"Restore not byte-identical for: {name!r}"

    if rc == 0:
        print("  SURVIVED: tests passed when they should have failed")
        return "SURVIVED"
    print(f"  DEAD: tests caught the mutation (exit {rc})")
    return "DEAD"


def _print_summary(results: list[tuple[str, str]]) -> None:
    """Print the results table and exit nonzero on survivors or DID-NOT-APPLY."""
    print("\n\n=== Mutant Results ===")
    print(f"{'Mutant':<55} {'Result'}")
    print("-" * 70)
    for name, result in results:
        print(f"{name:<55} {result}")

    survivors = [n for n, r in results if r == "SURVIVED"]
    did_not_apply = [
        n for n, r in results
        if r.startswith("DID-NOT-APPLY") or r.startswith("PATTERN")
    ]
    dead = [n for n, r in results if r == "DEAD"]
    print(
        f"\nDEAD: {len(dead)}, SURVIVED: {len(survivors)},"
        f" DID-NOT-APPLY: {len(did_not_apply)}"
    )
    if survivors:
        print("\nSURVIVING MUTANTS (tests are not load-bearing):")
        for n in survivors:
            print(f"  {n}")
        sys.exit(1)
    if did_not_apply:
        print("\nDID-NOT-APPLY (patterns not found in target file):")
        for n in did_not_apply:
            print(f"  {n}")
        sys.exit(2)
    print("\nAll mutants killed. Tests are load-bearing.")


def run_mutants() -> None:
    original_bytes = _WORKFLOW.read_bytes()
    results: list[tuple[str, str]] = []
    for name, old, new in _MUTANTS:
        print(f"\n--- Mutant: {name} ---")
        results.append((name, _run_one_mutant(name, old, new, original_bytes)))
    _print_summary(results)


if __name__ == "__main__":
    run_mutants()
