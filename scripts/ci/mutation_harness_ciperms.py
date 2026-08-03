#!/usr/bin/env python3
"""Mutation harness for CI security permission tests.

Tests four outcome classes per mutation:
  DEAD         - mutant introduced, test caught it (good)
  SURVIVED     - mutant introduced, test passed anyway (BAD - test is weak)
  DID-NOT-APPLY - target literal absent in file; patch was a no-op (harness defect)
  NOT-RUN      - pytest never reached a verdict (bad nodeid, collection error,
                 zero tests selected); the mutant is unmeasured, not killed

Exit codes:
  0 - every mutant DEAD
  1 - any SURVIVED, DID-NOT-APPLY, or NOT-RUN
  2 - a mutated file could not be restored (the tree is left dirty; recover
      with ``git checkout -- <file>`` before rerunning)

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
NOT_RUN = "NOT-RUN"

# pytest's documented exit codes. Only TESTS_FAILED means the test ran and
# rejected the mutant; the rest mean it never got a verdict.
_PYTEST_OK = 0
_PYTEST_TESTS_FAILED = 1
_PYTEST_RC_MEANING = {
    2: "interrupted",
    3: "internal error",
    4: "usage error (bad nodeid?)",
    5: "no tests collected",
}


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
        errors="replace",
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
    note = ""
    try:
        proc = _run_tests(mutation.test_filter)
        outcome, note = _classify(proc)
    finally:
        # Always restore.
        target.write_bytes(backup)

    # Verify restore.
    restored = target.read_bytes()
    if restored != backup:
        print(f"ERROR: restore of {target.name} failed!", file=sys.stderr)
        sys.exit(2)

    return Result(mutation, outcome, note)


def _classify(proc: subprocess.CompletedProcess[str]) -> tuple[str, str]:
    """Turn a pytest run into an outcome.

    Only exit 1 means the test ran and rejected the mutant. Treating every
    non-zero code as DEAD scores a typo'd nodeid (exit 4) or an empty
    selection (exit 5) as a kill, which is the one failure a mutation harness
    must not have: it reports strength it never measured.
    """
    if proc.returncode == _PYTEST_TESTS_FAILED:
        return DEAD, ""
    if proc.returncode == _PYTEST_OK:
        return SURVIVED, ""
    meaning = _PYTEST_RC_MEANING.get(proc.returncode, "unrecognized pytest exit code")
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    detail = tail[-1] if tail else "no output"
    return NOT_RUN, f"pytest exited {proc.returncode} ({meaning}): {detail}"


def build_mutations() -> list[Mutation]:
    wf_perms_test = REPO_ROOT / "tests/workflows/test_workflow_job_permissions.py"
    pr_val_test = REPO_ROOT / "tests/ci/test_pr_validation_workflow.py"
    pr_val_workflow = REPO_ROOT / ".github/workflows/pr-validation.yml"

    perms_gate = (
        "tests/workflows/test_workflow_job_permissions.py"
        "::test_no_job_silently_inherits_a_new_write_scope"
    )
    guard_class = (
        "tests/ci/test_pr_validation_workflow.py::TestBotSkipGuardClassification"
    )

    return [
        # --- Permissions ratchet mutations (test_workflow_job_permissions.py) ---

        # M1: Remove one job from _GRANDFATHERED. The live scan still finds it,
        # so found > grandfathered -> test must fail.
        Mutation(
            description="M1: drop ai-issue-triage from _GRANDFATHERED (new offender path)",
            target_file=wf_perms_test,
            old_bytes=b'        ("ai-issue-triage.yml", "ai-issue-triage"),\n',
            new_bytes=b"",
            test_filter=perms_gate,
        ),

        # M2: Add a fake entry to _GRANDFATHERED. The live scan won't find it,
        # so grandfathered > found -> test must fail (fixed-but-not-removed path).
        Mutation(
            description="M2: add non-existent job to _GRANDFATHERED (unrecorded-fix path)",
            target_file=wf_perms_test,
            old_bytes=b'        ("ai-issue-triage.yml", "ai-issue-triage"),\n',
            new_bytes=(
                b'        ("ai-issue-triage.yml", "ai-issue-triage"),\n'
                b'        ("fake-workflow.yml", "fake-job"),\n'
            ),
            test_filter=perms_gate,
        ),

        # M3: Make write_scopes miss the write-all shorthand.
        Mutation(
            description="M3: corrupt write_scopes to miss the write-all shorthand",
            target_file=wf_perms_test,
            old_bytes=b'        return ["ALL"] if permissions == "write-all" else []\n',
            new_bytes=b"        return []\n",
            test_filter="tests/workflows/test_workflow_job_permissions.py"
            "::TestWriteScopes::test_write_all_shorthand_reports_all",
        ),

        # M4: Make jobs_inheriting_write bail before it reports anything.
        Mutation(
            description="M4: corrupt jobs_inheriting_write to report nothing",
            target_file=wf_perms_test,
            old_bytes=b"    if not inherited:\n        return {}\n",
            new_bytes=b"    if True:\n        return {}\n",
            test_filter="tests/workflows/test_workflow_job_permissions.py"
            "::TestJobsInheritingWrite::test_a_job_with_no_block_inherits",
        ),

        # M5: Remove the job-has-own-block guard from jobs_inheriting_write.
        Mutation(
            description="M5: remove own-block exclusion from jobs_inheriting_write",
            target_file=wf_perms_test,
            old_bytes=b'    return {name: inherited for name, job in _jobs(doc).items() '
            b'if "permissions" not in job}\n',
            new_bytes=b"    return {name: inherited for name, job in _jobs(doc).items()}\n",
            test_filter="tests/workflows/test_workflow_job_permissions.py"
            "::TestJobsInheritingWrite::test_a_job_with_its_own_block_is_clean",
        ),

        # --- Bot-skip classification mutations (test_pr_validation_workflow.py) ---

        # M6: Put a phantom name in the allowlist. No step carries it, so the
        # stale-entry test must fail.
        Mutation(
            description="M6: add a phantom name to _ALLOWED_BEHIND_GUARD (stale-entry path)",
            target_file=pr_val_test,
            old_bytes=b'            "Enforce Blocking Issues",\n',
            new_bytes=b'            "Enforce Blocking Issues",\n            "No Such Step",\n',
            test_filter=f"{guard_class}::test_all_allowed_guarded_steps_are_present",
        ),

        # M7: Put the ADR-006 correctness gate back behind the skip guard.
        Mutation(
            description="M7: re-add bot-skip guard to the ADR-006 ratchet step",
            target_file=pr_val_workflow,
            # Anchor on the step name alone. It is unique in the workflow, and
            # the mutation is the inserted `if:` line, not the scanner's --max
            # value. An earlier literal carried `--max 58`; PR #4406 ratcheted
            # that to 0 and this mutation went un-runnable until someone noticed.
            old_bytes=b"      - name: Run ADR-006 run-block ratchet\n",
            new_bytes=(
                b"      - name: Run ADR-006 run-block ratchet\n"
                b"        if: steps.should-run.outputs.skip != 'true'\n"
            ),
            test_filter=f"{guard_class}::test_adr006_ratchet_is_unconditional",
        ),

        # M8: Drop a throughput step from the allowlist while it stays guarded.
        # It then reads as an unjustified gate behind the skip guard.
        Mutation(
            description="M8: drop Post PR Comment from the allowlist (unjustified-gate path)",
            target_file=pr_val_test,
            old_bytes=b'            "Post PR Comment",\n',
            new_bytes=b"",
            test_filter=f"{guard_class}::test_no_security_gate_is_skip_guarded",
        ),

        # M9: Put a security gate behind the skip guard in the workflow itself.
        Mutation(
            description="M9: add bot-skip guard to Validate workflow YAML (security gate)",
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
            test_filter=f"{guard_class}::test_no_security_gate_is_skip_guarded",
        ),
    ]


def _verify_repo_root() -> None:
    """Refuse to mutate anything unless REPO_ROOT is a real worktree.

    ``REPO_ROOT`` is derived from this file's own path, so ``cd`` cannot
    redirect it. What it does not prove is that the tree is intact: run this
    from a stripped copy, an export, or a partially-checked-out worktree and
    the first write lands on a file with no way to ``git checkout`` it back.
    Checking before the first write turns that into an error instead of an
    unrecoverable edit.
    """
    if not (REPO_ROOT / ".git").exists():
        raise SystemExit(
            f"config error: {REPO_ROOT} is not a git worktree, refusing to "
            "mutate tracked files with no way to restore them"
        )


def main() -> int:
    _verify_repo_root()
    mutations = build_mutations()
    results: list[Result] = []

    for m in mutations:
        r = apply_mutation(m)
        results.append(r)
        icon = {"DEAD": "✓", "SURVIVED": "✗", "DID-NOT-APPLY": "?", "NOT-RUN": "!"}.get(
            r.outcome, "?"
        )
        note = f" -- {r.note}" if r.note else ""
        print(f"[{icon}] {r.outcome:15s}  {r.mutation.description}{note}")

    dead = sum(1 for r in results if r.outcome == DEAD)
    survived = sum(1 for r in results if r.outcome == SURVIVED)
    dna = sum(1 for r in results if r.outcome == DID_NOT_APPLY)
    not_run = sum(1 for r in results if r.outcome == NOT_RUN)

    print()
    print(f"DEAD:          {dead}")
    print(f"SURVIVED:      {survived}")
    print(f"DID-NOT-APPLY: {dna}")
    print(f"NOT-RUN:       {not_run}")

    if survived:
        print("\nERROR: surviving mutants mean the tests do not cover those behaviors.")
        return 1
    if not_run:
        print(
            "\nERROR: NOT-RUN means pytest never reached a verdict, so those "
            "mutants are unmeasured rather than killed."
        )
        return 1
    if dna:
        print("\nERROR: DID-NOT-APPLY means a literal was missing or ambiguous.")
        return 1
    print(f"\nAll {dead} mutants killed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
