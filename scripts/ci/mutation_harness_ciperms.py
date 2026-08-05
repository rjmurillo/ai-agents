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

import os
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from shlex import quote

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
    expected_outcome: str = DEAD


@dataclass
class Result:
    mutation: Mutation
    outcome: str
    note: str = ""


def _purge_pycache(mutated_files: Iterable[Path]) -> subprocess.CompletedProcess[str] | None:
    """Delete stale bytecode before pytest can import a mutated file."""
    for pycache in {path.parent / "__pycache__" for path in mutated_files}:
        if not pycache.exists():
            continue
        try:
            shutil.rmtree(pycache)
        except OSError as exc:
            return subprocess.CompletedProcess(
                ["purge", str(pycache)],
                4,
                "",
                f"could not purge {pycache}: {exc}",
            )
    return None


def _run_tests(
    test_filter: str, mutated_files: Iterable[Path] = ()
) -> subprocess.CompletedProcess[str]:
    purge_error = _purge_pycache(mutated_files)
    if purge_error is not None:
        return purge_error
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
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
        env=env,
        cwd=REPO_ROOT,
    )


def _recovery_checkout_hint(targets: Iterable[Path]) -> str:
    quoted_targets = " ".join(quote(str(target)) for target in targets)
    return f"git checkout -- {quoted_targets}"


def _dirty_paths(backups: Mapping[Path, bytes | None]) -> list[Path]:
    dirty: list[Path] = []
    for target, backup in backups.items():
        if backup is None:
            dirty.append(target)
            continue
        try:
            if target.read_bytes() != backup:
                dirty.append(target)
        except OSError:
            dirty.append(target)
    return dirty


def _restore_backups(
    backups: Mapping[Path, bytes | None], prior_error: BaseException | None = None
) -> None:
    """Restore mutated files or exit 2 with the dirty file list."""
    failures: list[tuple[Path, str, BaseException | None]] = []
    for target, backup in backups.items():
        if backup is None:
            failures.append((target, "backup missing", None))
            continue
        try:
            target.write_bytes(backup)
        except OSError as exc:
            failures.append((target, str(exc), exc))

    for target, backup in backups.items():
        if backup is None:
            continue
        try:
            restored = target.read_bytes()
        except OSError as exc:
            failures.append((target, f"could not verify restore: {exc}", exc))
            continue
        if restored != backup:
            failures.append((target, "bytes differ after restore write", None))

    if not failures:
        return

    dirty = _dirty_paths(backups) or list(backups)
    first_failure = failures[0][2]
    label = dirty[0].name if len(dirty) == 1 else f"{len(dirty)} files"
    details = "; ".join(f"{path}: {reason}" for path, reason, _exc in failures)
    if prior_error is not None:
        details = f"{details}; original error before restore failed: {prior_error!r}"
    file_list = "\n".join(f"  - {path}" for path in dirty)
    print(
        f"ERROR: restore of {label} failed! {details}\n"
        f"Dirty files:\n{file_list}\n"
        f"Run: {_recovery_checkout_hint(dirty)}",
        file=sys.stderr,
    )
    raise SystemExit(2) from first_failure


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
    prior_error: BaseException | None = None
    try:
        proc = _run_tests(mutation.test_filter, (target,))
        outcome, note = _classify(proc)
    except BaseException as exc:
        prior_error = exc
        raise
    finally:
        _restore_backups({target: backup}, prior_error)

    return Result(mutation, outcome, note)


def _classify(proc: subprocess.CompletedProcess[str]) -> tuple[str, str]:
    """Turn a pytest run into an outcome.

    Only exit 1 means the test ran and rejected the mutant. Treating every
    non-zero code as DEAD scores a typo'd nodeid (exit 4) or an empty
    selection (exit 5) as a kill, which is the one failure a mutation harness
    must not have: it reports strength it never measured.
    """
    output = f"{proc.stdout}\n{proc.stderr}".lower()
    if "no tests ran" in output or "collected 0 items" in output:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        last_line = detail[-1] if detail else "no output"
        return NOT_RUN, f"pytest collected zero tests: {last_line}"
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
            old_bytes=(
                b"      - name: Run ADR-006 run-block ratchet\n"
                b"        run: python3 scripts/ci/adr006_run_block_scanner.py --max 0\n"
            ),
            new_bytes=(
                b"      - name: Run ADR-006 run-block ratchet\n"
                b"        if: steps.should-run.outputs.skip != 'true'\n"
                b"        run: python3 scripts/ci/adr006_run_block_scanner.py --max 0\n"
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

        # M10: Cosmetic control. Rewording a docstring must survive, or the
        # harness is measuring noise rather than load-bearing behavior.
        Mutation(
            description="M10: cosmetic control rewords a module docstring",
            target_file=wf_perms_test,
            old_bytes=(
                b"A job with no ``permissions:`` block silently inherits the "
                b"workflow-level one.\n"
            ),
            new_bytes=(
                b"A job with no ``permissions:`` block quietly inherits the "
                b"workflow-level one.\n"
            ),
            test_filter=perms_gate,
            expected_outcome=SURVIVED,
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
        icon = "✓" if r.outcome == m.expected_outcome else "✗"
        note = f" -- {r.note}" if r.note else ""
        expected = f" expected {m.expected_outcome}" if r.outcome != m.expected_outcome else ""
        print(f"[{icon}] {r.outcome:15s}  {r.mutation.description}{expected}{note}")

    dead = sum(1 for r in results if r.outcome == DEAD)
    survived = sum(1 for r in results if r.outcome == SURVIVED)
    dna = sum(1 for r in results if r.outcome == DID_NOT_APPLY)
    not_run = sum(1 for r in results if r.outcome == NOT_RUN)

    print()
    print(f"DEAD:          {dead}")
    print(f"SURVIVED:      {survived}")
    print(f"DID-NOT-APPLY: {dna}")
    print(f"NOT-RUN:       {not_run}")

    unexpected = [r for r in results if r.outcome != r.mutation.expected_outcome]
    if unexpected:
        print("\nERROR: unexpected mutation outcomes:")
        for result in unexpected:
            print(
                f"  {result.mutation.description}: expected "
                f"{result.mutation.expected_outcome}, got {result.outcome}"
            )
        if any(r.outcome == SURVIVED for r in unexpected):
            print("Surviving non-control mutants mean the tests do not cover those behaviors.")
        if any(r.outcome == DEAD and r.mutation.expected_outcome == SURVIVED for r in unexpected):
            print("A cosmetic control died, so the harness is measuring noise.")
        if any(r.outcome == NOT_RUN for r in unexpected):
            print(
                "NOT-RUN means pytest never reached a verdict, so those "
                "mutants are unmeasured rather than killed."
            )
        if any(r.outcome == DID_NOT_APPLY for r in unexpected):
            print("DID-NOT-APPLY means a literal was missing or ambiguous.")
        return 1
    print(f"\nAll {len(results)} mutants matched expected outcomes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
