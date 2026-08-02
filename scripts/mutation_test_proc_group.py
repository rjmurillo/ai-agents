#!/usr/bin/env python3
"""Mutation harness for process-group timeout fix.

Verifies each load-bearing component of the fix individually.  For each
mutation:
1. Apply the change to the source file.
2. Run the targeted test file.
3. Assert the suite goes RED (at least one test fails).
4. Restore the original source.

Also runs one inversion (the correct code) that MUST STAY GREEN, and
asserts the baseline is green before and after the mutations.

Exit 0 = all mutations killed, inverted-control green, baseline green.
Exit non-zero = a mutation survived (test gap) or setup failure.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GHP = ROOT / "scripts" / "validation" / "git_hook_policy.py"
WLT = ROOT / "scripts" / "validation" / "run_workflow_local_test.py"

GHP_TESTS = ROOT / "tests" / "validation" / "test_run_command_proc_group.py"
WLT_TESTS = ROOT / "tests" / "validation" / "test_run_workflow_local_test.py"

PYTEST = ["uv", "run", "--frozen", "python", "-m", "pytest"]


def run_tests(test_file: Path, label: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*PYTEST, str(test_file), "-q", "--tb=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def assert_red(result: subprocess.CompletedProcess[str], mutation_name: str) -> None:
    output = result.stdout + result.stderr
    if "no tests ran" in output:
        print(f"  FAIL (no tests ran): {mutation_name}")
        sys.exit(1)
    if result.returncode == 4:
        print(f"  FAIL (pytest usage error rc=4): {mutation_name}")
        sys.exit(1)
    if result.returncode == 0:
        print(f"  SURVIVED (suite stayed green - test gap): {mutation_name}")
        sys.exit(1)
    print(f"  KILLED ok: {mutation_name}")


def assert_green(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode != 0:
        print(f"  FAIL (suite should be green for {label})")
        print(result.stdout[-2000:])
        sys.exit(1)
    print(f"  GREEN ok: {label}")


def mutate(path: Path, old: str, new: str, mutation_name: str) -> bytes:
    original = path.read_bytes()
    text = original.decode()
    count = text.count(old)
    if count == 0:
        print(f"  FAIL (mutation did not apply - 0 occurrences of target): {mutation_name}")
        sys.exit(1)
    path.write_text(text.replace(old, new), encoding="utf-8")
    return original


def restore(path: Path, original: bytes) -> None:
    path.write_bytes(original)


mutations: list[tuple[Path, Path, str, str, str]] = [
    # (source_file, test_file, old_text, new_text, name)

    # M1: Remove start_new_session in _run_command (git_hook_policy)
    (
        GHP,
        GHP_TESTS,
        "start_new_session=_SUPPORTS_PGROUP,",
        "start_new_session=False,",
        "M1-start_new_session-False-ghp",
    ),

    # M2: Replace _killpg_safe call in _run_command with proc.kill()
    (
        GHP,
        GHP_TESTS,
        "_killpg_safe(proc.pid)",
        "proc.kill()  # MUTANT: no group kill",
        "M2-killpg_safe-replaced-with-proc.kill",
    ),

    # M3: Remove start_new_session in _run (run_workflow_local_test)
    (
        WLT,
        WLT_TESTS,
        "start_new_session=_supports_pgroup,",
        "start_new_session=False,",
        "M3-start_new_session-False-wlt",
    ),

    # M4: Replace _killpg_safe call in _run with proc.kill()
    (
        WLT,
        WLT_TESTS,
        "_killpg_safe(proc.pid)",
        "proc.kill()  # MUTANT: no group kill",
        "M4-killpg_safe-replaced-with-proc.kill-wlt",
    ),
]

# Inverted control: the CORRECT code must stay green
inverted_controls: list[tuple[Path, str]] = [
    (GHP_TESTS, "inverted-control: GHP tests green with correct code"),
    (WLT_TESTS, "inverted-control: WLT tests green with correct code"),
]


def main() -> None:
    print("=== Mutation harness: process-group timeout fix ===\n")

    # Baseline green check
    print("[Baseline] Checking tests are green before mutations...")
    for test_file, label in inverted_controls:
        r = run_tests(test_file, label)
        assert_green(r, label)
    print()

    for source_file, test_file, old_text, new_text, name in mutations:
        print(f"[Mutation] {name}")
        original = mutate(source_file, old_text, new_text, name)
        try:
            r = run_tests(test_file, name)
            assert_red(r, name)
        finally:
            restore(source_file, original)
    print()

    # Inverted control (correct code) must stay green
    print("[Inverted controls] Verifying correct code stays green...")
    for test_file, label in inverted_controls:
        r = run_tests(test_file, label)
        assert_green(r, label)
    print()

    # Final baseline restore verification
    print("[Baseline] Final green check after all mutations restored...")
    for test_file, label in inverted_controls:
        r = run_tests(test_file, label)
        assert_green(r, label)
    print()

    print("=== All mutations killed. Harness passed. ===")


if __name__ == "__main__":
    main()
