#!/usr/bin/env python3
"""Mutation harness for CI security permission tests.

Tests three outcome classes per mutation:
  DEAD         - mutant introduced, test caught it (good)
  SURVIVED     - mutant introduced, test passed anyway (BAD - test is weak)
  DID-NOT-APPLY - target literal absent in file; patch was a no-op (harness defect)

Exit code: 0 if every mutant is DEAD, 1 otherwise.

Usage:
    uv run --frozen python3 scripts/ci/mutation_harness_ciperms.py
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEAD = "DEAD"
SURVIVED = "SURVIVED"
DID_NOT_APPLY = "DID-NOT-APPLY"


@dataclass
class Mutation:
    description: str
    target_file: Path
    old_bytes: bytes
    new_bytes: bytes
    test_filter: str


@dataclass
class Result:
    mutation: Mutation
    outcome: str
    note: str = ""


def _run_tests(test_filter: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "uv",
            "run",
            "--frozen",
            "python",
            "-m",
            "pytest",
            "-x",
            "-q",
            "--no-header",
            test_filter,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
    )


def apply_mutation(mutation: Mutation) -> Result:
    """Apply mutation, run tests, restore file, return outcome."""
    target = mutation.target_file
    backup = target.read_bytes()

    # Verify the target literal is present (DID-NOT-APPLY guard).
    if mutation.old_bytes not in backup:
        return Result(
            mutation,
            DID_NOT_APPLY,
            f"literal {mutation.old_bytes[:60]!r} not found in {target.name}",
        )

    # Apply exactly one occurrence.
    count = backup.count(mutation.old_bytes)
    if count != 1:
        # Multiple occurrences: refuse ambiguous mutation.
        return Result(
            mutation,
            DID_NOT_APPLY,
            f"found {count} occurrences of target literal; expected exactly 1",
        )

    mutated = backup.replace(mutation.old_bytes, mutation.new_bytes, 1)

    # cmp guard: patch must have changed the file.
    if mutated == backup:
        return Result(mutation, DID_NOT_APPLY, "file byte-identical after patch")

    target.write_bytes(mutated)
    try:
        proc = _run_tests(mutation.test_filter)
        if proc.returncode != 0:
            outcome = DEAD
        else:
            outcome = SURVIVED
    finally:
        # Always restore.
        target.write_bytes(backup)

    # Verify restore.
    restored = target.read_bytes()
    if restored != backup:
        print(f"ERROR: restore of {target.name} failed!", file=sys.stderr)
        sys.exit(2)

    return Result(mutation, outcome)


def build_mutations() -> list[Mutation]:
    wf_perms_test = REPO_ROOT / "tests/workflows/test_workflow_job_permissions.py"
    pr_val_test = REPO_ROOT / "tests/ci/test_pr_validation_workflow.py"
    pr_val_workflow = REPO_ROOT / ".github/workflows/pr-validation.yml"

    return [
        # --- Permissions ratchet mutations (test_workflow_job_permissions.py) ---

        # M1: Remove one job from _GRANDFATHERED. The live scan still finds it,
        # so live > grandfathered -> test must fail.
        Mutation(
            description="M1: drop ai-issue-triage from _GRANDFATHERED (new offender path)",
            target_file=wf_perms_test,
            old_bytes=b'        ("ai-issue-triage.yml", "ai-issue-triage"),\n',
            new_bytes=b"",
            test_filter="tests/workflows/test_workflow_job_permissions.py"
            "::test_over_granted_jobs_match_grandfathered_set",
        ),

        # M2: Add a fake entry to _GRANDFATHERED. The live scan won't find it,
        # so grandfathered > live -> test must fail (fixed-but-not-removed path).
        Mutation(
            description="M2: add non-existent job to _GRANDFATHERED (unrecorded-fix path)",
            target_file=wf_perms_test,
            old_bytes=b'        ("ai-issue-triage.yml", "ai-issue-triage"),\n',
            new_bytes=(
                b'        ("ai-issue-triage.yml", "ai-issue-triage"),\n'
                b'        ("fake-workflow.yml", "fake-job"),\n'
            ),
            test_filter="tests/workflows/test_workflow_job_permissions.py"
            "::test_over_granted_jobs_match_grandfathered_set",
        ),

        # M3: Make write_scopes return [] for "write-all" (wrong logic).
        Mutation(
            description="M3: corrupt write_scopes to miss write-all string",
            target_file=wf_perms_test,
            old_bytes=b'    if perms == "write-all":\n        return ["ALL"]\n',
            new_bytes=b'    if perms == "write-all":\n        return []\n',
            test_filter="tests/workflows/test_workflow_job_permissions.py"
            "::TestWriteScopes::test_write_all_string_returns_ALL",
        ),

        # M4: Make over_granted skip its write check (always returns empty).
        Mutation(
            description="M4: corrupt over_granted to skip write-scope filter",
            target_file=wf_perms_test,
            old_bytes=b"    wf_write = write_scopes(doc.get(\"permissions\"))\n"
            b"    if not wf_write:\n        return []\n",
            new_bytes=b"    wf_write = write_scopes(doc.get(\"permissions\"))\n"
            b"    if True:\n        return []\n",
            test_filter="tests/workflows/test_workflow_job_permissions.py"
            "::TestOverGranted::test_job_without_own_block_is_returned",
        ),

        # M5: Remove the job-has-own-block guard from over_granted.
        Mutation(
            description="M5: remove own-block exclusion from over_granted",
            target_file=wf_perms_test,
            old_bytes=b"        if \"permissions\" in job:\n            continue\n",
            new_bytes=b"",
            test_filter="tests/workflows/test_workflow_job_permissions.py"
            "::TestOverGranted::test_job_with_own_block_is_excluded",
        ),

        # --- Bot-skip classification mutations (test_pr_validation_workflow.py) ---

        # M6: Add ADR-006 to _THROUGHPUT_STEPS (wrong class).
        # test_security_gate_is_not_behind_bot_skip_guard[Run ADR-006] must fail
        # because the step would be in both sets, BUT the throughput test would
        # find a step with no condition and fail first. The DEAD outcome is still
        # correct; the test catches the wrong state.
        # Actually: the security test passes (step has no if), the throughput
        # test fails (step has no if == _BOT_SKIP_CONDITION). Either way, DEAD.
        Mutation(
            description="M6: mis-classify ADR-006 step as throughput (wrong class)",
            target_file=pr_val_test,
            old_bytes=b'        "Run ADR-006 run-block ratchet",\n',
            new_bytes=b"",
            test_filter="tests/ci/test_pr_validation_workflow.py::TestBotSkipClassification"
            "::test_security_gate_is_not_behind_bot_skip_guard[Run ADR-006 run-block ratchet]",
        ),

        # M7: Restore the bot-skip condition on the ADR-006 workflow step.
        # The security-gate classification test must then fail.
        Mutation(
            description="M7: re-add bot-skip guard to ADR-006 workflow step",
            target_file=pr_val_workflow,
            old_bytes=(
                b"      - name: Run ADR-006 run-block ratchet\n"
                b"        run: python3 scripts/ci/adr006_run_block_scanner.py --max 58\n"
            ),
            new_bytes=(
                b"      - name: Run ADR-006 run-block ratchet\n"
                b"        if: steps.should-run.outputs.skip != 'true'\n"
                b"        run: python3 scripts/ci/adr006_run_block_scanner.py --max 58\n"
            ),
            test_filter="tests/ci/test_pr_validation_workflow.py::TestBotSkipClassification"
            "::test_security_gate_is_not_behind_bot_skip_guard[Run ADR-006 run-block ratchet]",
        ),

        # M8: Remove the bot-skip condition from a throughput step in the workflow.
        # The throughput classification test must then fail.
        Mutation(
            description="M8: remove bot-skip condition from throughput step in workflow",
            target_file=pr_val_workflow,
            old_bytes=(
                b"      - name: Validate PR Description vs Diff\n"
                b"        if: steps.should-run.outputs.skip != 'true'\n"
            ),
            new_bytes=b"      - name: Validate PR Description vs Diff\n",
            test_filter="tests/ci/test_pr_validation_workflow.py::TestBotSkipClassification"
            "::test_throughput_step_is_behind_bot_skip_guard[Validate PR Description vs Diff]",
        ),

        # M9: Add a bot-skip condition to a security gate step in the workflow.
        # The security-gate classification test must then fail.
        Mutation(
            description="M9: add bot-skip condition to Validate workflow YAML (security gate)",
            target_file=pr_val_workflow,
            old_bytes=(
                b"      - name: Validate workflow YAML\n"
                b"        run: uv run --frozen python3 scripts/validate_workflows.py\n"
            ),
            new_bytes=(
                b"      - name: Validate workflow YAML\n"
                b"        if: steps.should-run.outputs.skip != 'true'\n"
                b"        run: uv run --frozen python3 scripts/validate_workflows.py\n"
            ),
            test_filter="tests/ci/test_pr_validation_workflow.py::TestBotSkipClassification"
            "::test_security_gate_is_not_behind_bot_skip_guard[Validate workflow YAML]",
        ),
    ]


def main() -> int:
    mutations = build_mutations()
    results: list[Result] = []

    for m in mutations:
        r = apply_mutation(m)
        results.append(r)
        icon = {"DEAD": "✓", "SURVIVED": "✗", "DID-NOT-APPLY": "?"}.get(r.outcome, "?")
        note = f" -- {r.note}" if r.note else ""
        print(f"[{icon}] {r.outcome:15s}  {r.mutation.description}{note}")

    dead = sum(1 for r in results if r.outcome == DEAD)
    survived = sum(1 for r in results if r.outcome == SURVIVED)
    dna = sum(1 for r in results if r.outcome == DID_NOT_APPLY)

    print()
    print(f"DEAD:          {dead}")
    print(f"SURVIVED:      {survived}")
    print(f"DID-NOT-APPLY: {dna}")

    if survived:
        print("\nERROR: surviving mutants mean the tests do not cover those behaviors.")
        return 1
    if dna:
        print("\nERROR: DID-NOT-APPLY means a literal was missing or ambiguous.")
        return 1
    print(f"\nAll {dead} mutants killed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
