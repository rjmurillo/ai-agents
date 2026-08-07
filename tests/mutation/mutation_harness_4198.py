"""Mutation harness for issues #4198/#4195: prose portability CI wiring.

Verifies that each new structural property added to validate-vendor-portability.yml
is individually load-bearing by mutating the file and asserting the wiring tests
detect the regression.

Rules:
- Count each pattern; report DID-NOT-APPLY when count != 1.
- cmp byte-identical after mutation to confirm the patch actually changed the file.
- Clear __pycache__ after every file write.
- Assert byte-identical restore after every mutant.
- Include one inverted control that must SURVIVE.
- Three outcomes: DEAD (test caught it), SURVIVED (test missed it), DID-NOT-APPLY (pattern absent).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "validate-vendor-portability.yml"
_TESTS = [
    "tests/ci/test_validate_vendor_portability_wiring.py",
]

_MUTANTS: list[tuple[str, bytes, bytes, str]] = [
    (
        "remove prose portability step from validate-portability job",
        (
            b"\n      - name: Check skill prose portability ratchet"
            b"\n        run: uv run --frozen python"
            b" scripts/validation/check_skill_md_portability.py"
        ),
        b"",
        "DEAD",
    ),
    (
        "gate validation job on a change-detector result",
        (b"  validate-portability:\n    name: Validate Vendor Portability\n"),
        (
            b"  validate-portability:\n"
            b"    name: Validate Vendor Portability\n"
            b"    if: needs.check-changes.outputs.skills == 'true'\n"
        ),
        "DEAD",
    ),
    (
        "add an event-level paths-ignore filter",
        b"  push:\n    branches:\n      - main\n",
        (b"  push:\n    branches:\n      - main\n    paths-ignore:\n      - 'docs/**'\n"),
        "DEAD",
    ),
    (
        "replace run command with wrong script",
        (b"        run: uv run --frozen python scripts/validation/check_skill_md_portability.py\n"),
        (b"        run: uv run --frozen python scripts/validation/XYZZY_WRONG_SCRIPT.py\n"),
        "DEAD",
    ),
    (
        "inverted control: reword an unrelated workflow comment",
        b"# run them because a per-change path filter can report green without measuring.\n",
        b"# execute them because a path filter can report green without measuring.\n",
        "SURVIVED",
    ),
]


def _clear_pycache() -> None:
    for path in _REPO_ROOT.rglob("__pycache__"):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)


def _run_tests() -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *_TESTS, "-x", "-q"],
        cwd=_REPO_ROOT,
        capture_output=True,
    )


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
    expected: str,
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
    _clear_pycache()
    result = _run_tests()
    _WORKFLOW.write_bytes(original_bytes)
    _clear_pycache()
    restored = _WORKFLOW.read_bytes()
    assert restored == original_bytes, f"Restore not byte-identical for: {name!r}"

    output = result.stdout + result.stderr
    if result.returncode not in (0, 1) or b"no tests ran" in output:
        print("  HARNESS-ERROR: pytest did not run the target tests")
        return "HARNESS-ERROR"

    actual = "SURVIVED" if result.returncode == 0 else "DEAD"
    print(f"  {actual}: expected {expected}, pytest exit {result.returncode}")
    return actual


def _print_summary(results: list[tuple[str, str, str]]) -> None:
    """Print results and exit nonzero when an outcome differs from expectation."""
    print("\n\n=== Mutant Results ===")
    print(f"{'Mutant':<55} {'Expected':<10} {'Actual'}")
    print("-" * 82)
    for name, actual, expected in results:
        print(f"{name:<55} {expected:<10} {actual}")

    failures = [
        (name, expected, actual) for name, actual, expected in results if actual != expected
    ]
    if failures:
        print("\nUNEXPECTED MUTATION OUTCOMES:")
        for name, expected, actual in failures:
            print(f"  {name}: expected {expected}, got {actual}")
        sys.exit(2)
    print("\nAll load-bearing mutants died. Inverted control survived.")


def run_mutants() -> None:
    original_bytes = _WORKFLOW.read_bytes()
    results: list[tuple[str, str, str]] = []
    for name, old, new, expected in _MUTANTS:
        print(f"\n--- Mutant: {name} ---")
        actual = _run_one_mutant(name, old, new, original_bytes, expected)
        results.append((name, actual, expected))
    _print_summary(results)


if __name__ == "__main__":
    run_mutants()
