#!/usr/bin/env python3
"""Mutation harness for _check_non_fast_forward (issue #4293).

Verifies that each load-bearing line in the force-push detection guard is
individually necessary. Each mutation removes or inverts one condition; the
targeted tests must catch it.

Exit codes:
    0  - all mutations killed, baseline restored green
    1  - one or more mutations survived (test suite does not catch a defect)
    2  - configuration error (file not found, mutation did not apply, etc.)

Run from the worktree root:
    uv run --frozen python tests/mutation/mutation_harness_4293.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

TARGET_FILE = Path("scripts/validation/git_hook_policy.py")
BACKUP_FILE = Path("scripts/validation/git_hook_policy.py.mutation_bak")
TARGET_TESTS = [
    "tests/test_lefthook_integration.py::test_non_fast_forward_passes_on_fast_forward_push",
    "tests/test_lefthook_integration.py::test_non_fast_forward_blocks_history_rewrite",
    "tests/test_lefthook_integration.py::test_non_fast_forward_passes_new_branch",
    "tests/test_lefthook_integration.py::test_non_fast_forward_passes_deletion",
    "tests/test_lefthook_integration.py::test_non_fast_forward_returns_2_when_remote_object_absent",
    "tests/test_lefthook_integration.py::test_non_fast_forward_skips_non_branch_refs",
    "tests/test_lefthook_integration.py::test_non_fast_forward_env_var_bypasses_block",
    "tests/test_lefthook_integration.py::test_check_push_refs_blocks_force_push_end_to_end",
    "tests/test_lefthook_integration.py::test_check_push_refs_multi_ref_catches_second_rewrite",
]

MUTATIONS: list[tuple[str, str, str]] = [
    # (name, original_fragment, replacement_fragment)
    (
        "drop_non_branch_guard",
        "    if _branch_name(push_ref.remote_ref) is None:\n        return 0\n",
        "    if False:  # MUTANT: dropped non-branch guard\n        return 0\n",
    ),
    (
        "drop_new_branch_and_deletion_guard",
        "    if push_ref.is_deletion or push_ref.is_new:\n        return 0\n",
        "    if False:  # MUTANT: dropped new-branch/deletion guard\n        return 0\n",
    ),
    (
        "invert_absent_object_check",
        "    if not _commit_ref_exists(repo_root, push_ref.remote_sha):\n",
        "    if _commit_ref_exists(repo_root, push_ref.remote_sha):  # MUTANT\n",
    ),
    (
        "flip_ancestry_return",
        (
            "    if result.returncode == 0:\n"
            "        # remote_sha is an ancestor of local_sha: fast-forward push.\n"
            "        return 0\n"
        ),
        (
            "    if result.returncode != 0:  # MUTANT: flipped ancestry check\n"
            "        # remote_sha is an ancestor of local_sha: fast-forward push.\n"
            "        return 0\n"
        ),
    ),
    # Inverted control: a mutation that MUST survive (changing non-load-bearing
    # warning text does not affect test outcomes).
    (
        "SURVIVOR_change_warning_text",
        '            f"WARNING: force-push check bypassed via {FORCE_PUSH_OK_ENV}=1 "\n',
        '            f"INFO: force-push check bypassed via {FORCE_PUSH_OK_ENV}=1 "\n',
    ),
]


def _run_pytest(tests: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "--frozen", "python", "-m", "pytest", *tests, "-q", "--tb=no"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _apply_mutation(content: str, original: str, replacement: str) -> tuple[str, int]:
    count = content.count(original)
    if count == 0:
        return content, 0
    return content.replace(original, replacement, 1), count


def _verify_baseline() -> None:
    result = _run_pytest(TARGET_TESTS)
    if result.returncode != 0:
        print("ABORT: baseline is not green before mutation.", file=sys.stderr)
        print(result.stdout[-2000:], file=sys.stderr)
        sys.exit(2)
    # Verify test names appear in output (guards against "no tests ran").
    if "no tests ran" in result.stdout.lower() or "collected 0" in result.stdout:
        print("ABORT: no tests collected for baseline run.", file=sys.stderr)
        sys.exit(2)
    print(f"Baseline green: {result.stdout.strip().splitlines()[-1]}")


def _record_result(
    name: str,
    test_failed: bool,
    killed: list[str],
    survivors: list[str],
) -> None:
    is_survivor_control = name.startswith("SURVIVOR_")
    if is_survivor_control:
        if test_failed:
            print(f"  UNEXPECTED KILL on survivor control '{name}' -- harness error.")
            survivors.append(name)
        else:
            print(f"  OK (survived as expected): {name}")
            killed.append(f"(survived_control) {name}")
    elif test_failed:
        print(f"  KILLED: {name}")
        killed.append(name)
    else:
        print(f"  SURVIVED (tests did not catch mutation): {name}")
        survivors.append(name)


def main() -> None:
    if not TARGET_FILE.exists():
        print(f"ERROR: {TARGET_FILE} not found. Run from the worktree root.", file=sys.stderr)
        sys.exit(2)

    original_content = TARGET_FILE.read_text(encoding="utf-8")
    shutil.copy2(TARGET_FILE, BACKUP_FILE)

    _verify_baseline()

    survivors: list[str] = []
    killed: list[str] = []

    for name, original, replacement in MUTATIONS:
        mutated, apply_count = _apply_mutation(original_content, original, replacement)

        if apply_count == 0:
            print(f"ABORT: mutation '{name}' did not apply (fragment not found).", file=sys.stderr)
            TARGET_FILE.write_text(original_content, encoding="utf-8")
            BACKUP_FILE.unlink(missing_ok=True)
            sys.exit(2)

        # Verify the file actually changed.
        if mutated == original_content:
            print(f"ABORT: mutation '{name}' left file byte-identical.", file=sys.stderr)
            TARGET_FILE.write_text(original_content, encoding="utf-8")
            BACKUP_FILE.unlink(missing_ok=True)
            sys.exit(2)

        TARGET_FILE.write_text(mutated, encoding="utf-8")
        result = _run_pytest(TARGET_TESTS)

        # Restore immediately.
        TARGET_FILE.write_text(original_content, encoding="utf-8")

        # Sanity: no tests ran at all means the harness is broken.
        if result.returncode == 4 or "no tests ran" in result.stdout.lower():
            print(
                f"ABORT: mutation '{name}' caused pytest to collect no tests "
                f"(rc={result.returncode}).",
                file=sys.stderr,
            )
            BACKUP_FILE.unlink(missing_ok=True)
            sys.exit(2)

        test_failed = result.returncode != 0

        _record_result(name, test_failed, killed, survivors)

    # Final baseline verification.
    final = _run_pytest(TARGET_TESTS)
    if final.returncode != 0:
        print(
            "ERROR: baseline is red after mutation run -- file was not restored.",
            file=sys.stderr,
        )
        sys.exit(2)
    print(f"Final baseline green: {final.stdout.strip().splitlines()[-1]}")

    BACKUP_FILE.unlink(missing_ok=True)

    real_survivors = [s for s in survivors if not s.startswith("(survived_control)")]
    if real_survivors:
        print(
            f"\nFAIL: {len(real_survivors)} mutation(s) survived: {real_survivors}",
            file=sys.stderr,
        )
        sys.exit(1)

    killed_count = len([k for k in killed if not k.startswith("(survived_control)")])
    print(f"\nPASS: all {killed_count} mutations killed.")


if __name__ == "__main__":
    main()
