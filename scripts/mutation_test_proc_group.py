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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.testing.mutation_workspace import (  # noqa: E402
    isolated_mutation_worktree,
    purge_bytecode,
)

GHP_REL = Path("scripts") / "validation" / "git_hook_policy.py"
WLT_REL = Path("scripts") / "validation" / "run_workflow_local_test.py"
GHP_TESTS_REL = Path("tests") / "validation" / "test_run_command_proc_group.py"
WLT_TESTS_REL = Path("tests") / "validation" / "test_run_workflow_local_test.py"
TARGETS = (GHP_REL, WLT_REL)

PYTEST = ["uv", "run", "--frozen", "python", "-m", "pytest"]


def run_tests(
    repo_root: Path, test_file: Path, label: str
) -> subprocess.CompletedProcess[str]:
    purge_bytecode(repo_root)
    return subprocess.run(
        [*PYTEST, str(test_file), "-q", "--tb=no"],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
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


def _run_mutations(repo_root: Path) -> None:
    ghp = repo_root / GHP_REL
    wlt = repo_root / WLT_REL
    ghp_tests = repo_root / GHP_TESTS_REL
    wlt_tests = repo_root / WLT_TESTS_REL
    mutations: list[tuple[Path, Path, str, str, str]] = [
        (
            ghp,
            ghp_tests,
            "start_new_session=_SUPPORTS_PGROUP,",
            "start_new_session=False,",
            "M1-start_new_session-False-ghp",
        ),
        (
            ghp,
            ghp_tests,
            "_killpg_safe(proc.pid)",
            "proc.kill()  # MUTANT: no group kill",
            "M2-killpg_safe-replaced-with-proc.kill",
        ),
        (
            wlt,
            wlt_tests,
            "start_new_session=_supports_pgroup,",
            "start_new_session=False,",
            "M3-start_new_session-False-wlt",
        ),
        (
            wlt,
            wlt_tests,
            "_killpg_safe(proc.pid)",
            "proc.kill()  # MUTANT: no group kill",
            "M4-killpg_safe-replaced-with-proc.kill-wlt",
        ),
    ]
    inverted_controls: list[tuple[Path, str]] = [
        (ghp_tests, "inverted-control: GHP tests green with correct code"),
        (wlt_tests, "inverted-control: WLT tests green with correct code"),
    ]
    print("=== Mutation harness: process-group timeout fix ===\n")

    # Baseline green check
    print("[Baseline] Checking tests are green before mutations...")
    for test_file, label in inverted_controls:
        r = run_tests(repo_root, test_file, label)
        assert_green(r, label)
    print()

    for source_file, test_file, old_text, new_text, name in mutations:
        print(f"[Mutation] {name}")
        original = mutate(source_file, old_text, new_text, name)
        try:
            r = run_tests(repo_root, test_file, name)
            assert_red(r, name)
        finally:
            restore(source_file, original)
    print()

    # Inverted control (correct code) must stay green
    print("[Inverted controls] Verifying correct code stays green...")
    for test_file, label in inverted_controls:
        r = run_tests(repo_root, test_file, label)
        assert_green(r, label)
    print()

    # Final baseline restore verification
    print("[Baseline] Final green check after all mutations restored...")
    for test_file, label in inverted_controls:
        r = run_tests(repo_root, test_file, label)
        assert_green(r, label)
    print()

    print("=== All mutations killed. Harness passed. ===")


def main() -> None:
    with isolated_mutation_worktree(ROOT, TARGETS) as workspace:
        _run_mutations(workspace.root)


if __name__ == "__main__":
    main()
