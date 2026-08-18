#!/usr/bin/env python3
"""Mutation harness for CI security permission tests.

Outcomes: DEAD, SURVIVED, DID-NOT-APPLY, and NOT-RUN.
Exit 0 means every mutant matched its expected outcome.
Exit 1 means at least one outcome was unexpected.
Exit 2 means a mutated file could not be restored.
Usage: ``uv run --frozen python3 scripts/ci/mutation_harness_ciperms.py``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from shlex import quote

ACTIVE_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(ACTIVE_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(ACTIVE_REPO_ROOT))

from scripts.testing.mutation_workspace import (  # noqa: E402
    isolated_mutation_worktree,
    purge_bytecode,
)

REPO_ROOT = ACTIVE_REPO_ROOT
TARGETS = (
    Path("tests/workflows/test_workflow_job_permissions.py"),
    Path("tests/ci/test_pr_validation_workflow.py"),
    Path(".github/workflows/pr-validation.yml"),
)

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


def _run_tests(
    test_filter: str,
    repo_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    root = repo_root or REPO_ROOT
    try:
        purge_bytecode(root)
    except OSError as exc:
        return subprocess.CompletedProcess(
            ["purge", str(root)],
            4,
            "",
            f"could not purge bytecode below {root}: {exc}",
        )
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
        cwd=root,
    )


def _recovery_checkout_hint(targets: Path | Iterable[Path]) -> str:
    if isinstance(targets, Path):
        targets = [targets]
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


def _write_bytes_by_sibling_replace(target: Path, data: bytes, purpose: str) -> None:
    scratch = target.with_name(
        f".{target.name}.mutation-harness-{purpose}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        scratch.write_bytes(data)
        scratch.replace(target)
    except OSError:
        try:
            if scratch.exists():
                scratch.unlink()
        except OSError:
            pass
        raise


def _purge_mutation_bytecode(target: Path) -> str | None:
    try:
        purge_bytecode(target.parent)
    except OSError as exc:
        return f"pycache purge failed for {target.parent}: {exc}"
    return None


def _exit_restore_failed(
    target: Path,
    detail: str,
    prior_error: BaseException | None = None,
) -> None:
    if prior_error is not None:
        detail = f"{detail}; original error before restore failed: {prior_error!r}"
    print(
        f"ERROR: could not restore {target.name}: {detail}\n"
        f"Tree is dirty. Run: {_recovery_checkout_hint(target)}",
        file=sys.stderr,
    )
    raise SystemExit(2)


def apply_mutation(
    mutation: Mutation,
    repo_root: Path | None = None,
) -> Result:
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

    try:
        _write_bytes_by_sibling_replace(target, mutated, "mutant")
    except OSError as exc:
        return Result(mutation, DID_NOT_APPLY, f"could not write mutant: {exc}")

    note = ""
    prior_error: BaseException | None = None
    try:
        try:
            if target.read_bytes() != mutated:
                return Result(mutation, DID_NOT_APPLY, "mutant bytes differed after write")
        except OSError as exc:
            return Result(mutation, DID_NOT_APPLY, f"could not verify mutant write: {exc}")

        if purge_error := _purge_mutation_bytecode(target):
            return Result(mutation, NOT_RUN, purge_error)

        if repo_root is None:
            proc = _run_tests(mutation.test_filter)
        else:
            proc = _run_tests(mutation.test_filter, repo_root)
        outcome, note = _classify(proc)
    except BaseException as exc:
        prior_error = exc
        raise
    finally:
        try:
            _write_bytes_by_sibling_replace(target, backup, "restore")
        except OSError as exc:
            _exit_restore_failed(target, str(exc), prior_error)

    # Verify restore: write_bytes returned but bytes differ (external race).
    try:
        restored = target.read_bytes()
    except OSError as exc:
        _exit_restore_failed(
            target,
            f"could not verify restored bytes: {exc}",
            prior_error,
        )
    if restored != backup:
        _exit_restore_failed(target, "bytes differ after write", prior_error)

    return Result(mutation, outcome, note)


def _classify(proc: subprocess.CompletedProcess[str]) -> tuple[str, str]:
    """Turn a pytest run into a harness outcome."""
    if proc.args and proc.args[0] == "purge":
        detail = (proc.stderr or proc.stdout or "").strip()
        return NOT_RUN, f"pycache purge failed: {detail}"
    output = f"{proc.stdout}\n{proc.stderr}".lower()
    if "no tests ran" in output or "collected 0 items" in output:
        lines = (proc.stderr or proc.stdout or "").strip().splitlines()
        last_line = lines[-1] if lines else "no output"
        return NOT_RUN, f"pytest collected zero tests: {last_line}"
    if proc.returncode == _PYTEST_TESTS_FAILED:
        return DEAD, ""
    if proc.returncode == _PYTEST_OK:
        return SURVIVED, ""
    meaning = _PYTEST_RC_MEANING.get(proc.returncode, "unrecognized pytest exit code")
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    detail = tail[-1] if tail else "no output"
    return NOT_RUN, f"pytest exited {proc.returncode} ({meaning}): {detail}"


def build_mutations(repo_root: Path | None = None) -> list[Mutation]:
    root = repo_root or REPO_ROOT
    wf_perms_test = root / "tests/workflows/test_workflow_job_permissions.py"
    pr_val_test = root / "tests/ci/test_pr_validation_workflow.py"
    pr_val_workflow = root / ".github/workflows/pr-validation.yml"

    perms_gate = (
        "tests/workflows/test_workflow_job_permissions.py"
        "::test_no_job_silently_inherits_a_new_write_scope"
    )
    guard_class = "tests/ci/test_pr_validation_workflow.py::TestBotSkipGuardClassification"

    return [
        Mutation(
            description="M1: drop ai-metrics-analysis from _GRANDFATHERED (new offender path)",
            target_file=wf_perms_test,
            old_bytes=b'        ("ai-metrics-analysis.yml", "analyze-metrics"),\n',
            new_bytes=b"",
            test_filter=perms_gate,
        ),
        Mutation(
            description="M2: add non-existent job to _GRANDFATHERED (unrecorded-fix path)",
            target_file=wf_perms_test,
            old_bytes=b'        ("ai-metrics-analysis.yml", "analyze-metrics"),\n',
            new_bytes=(
                b'        ("ai-metrics-analysis.yml", "analyze-metrics"),\n'
                b'        ("fake-workflow.yml", "fake-job"),\n'
            ),
            test_filter=perms_gate,
        ),
        Mutation(
            description="M3: corrupt write_scopes to miss the write-all shorthand",
            target_file=wf_perms_test,
            old_bytes=b'        return ["ALL"] if permissions == "write-all" else []\n',
            new_bytes=b"        return []\n",
            test_filter="tests/workflows/test_workflow_job_permissions.py"
            "::TestWriteScopes::test_write_all_shorthand_reports_all",
        ),
        Mutation(
            description="M4: corrupt jobs_inheriting_write to report nothing",
            target_file=wf_perms_test,
            old_bytes=b"    if not inherited:\n        return {}\n",
            new_bytes=b"    if True:\n        return {}\n",
            test_filter="tests/workflows/test_workflow_job_permissions.py"
            "::TestJobsInheritingWrite::test_a_job_with_no_block_inherits",
        ),
        Mutation(
            description="M5: remove own-block exclusion from jobs_inheriting_write",
            target_file=wf_perms_test,
            old_bytes=b"    return {name: inherited for name, job in _jobs(doc).items() "
            b'if "permissions" not in job}\n',
            new_bytes=b"    return {name: inherited for name, job in _jobs(doc).items()}\n",
            test_filter="tests/workflows/test_workflow_job_permissions.py"
            "::TestJobsInheritingWrite::test_a_job_with_its_own_block_is_clean",
        ),
        Mutation(
            description="M6: add a phantom name to _ALLOWED_BEHIND_GUARD (stale-entry path)",
            target_file=pr_val_test,
            old_bytes=b'            "Enforce Blocking Issues",\n',
            new_bytes=b'            "Enforce Blocking Issues",\n            "No Such Step",\n',
            test_filter=f"{guard_class}::test_all_allowed_guarded_steps_are_present",
        ),
        Mutation(
            description="M7: re-add bot-skip guard to the ADR-006 ratchet step",
            target_file=pr_val_workflow,
            old_bytes=b"      - name: Run ADR-006 run-block ratchet\n",
            new_bytes=(
                b"      - name: Run ADR-006 run-block ratchet\n"
                b"        if: steps.should-run.outputs.skip != 'true'\n"
            ),
            test_filter=f"{guard_class}::test_adr006_ratchet_is_unconditional",
        ),
        Mutation(
            description="M8: drop Post PR Comment from the allowlist (unjustified-gate path)",
            target_file=pr_val_test,
            old_bytes=b'            "Post PR Comment",\n',
            new_bytes=b"",
            test_filter=f"{guard_class}::test_no_security_gate_is_skip_guarded",
        ),
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


def _verify_repo_root(repo_root: Path | None = None) -> None:
    """Refuse to mutate anything unless the repository root is a real worktree."""
    root = repo_root or REPO_ROOT
    if not (root / ".git").exists():
        raise SystemExit(
            f"config error: {root} is not a git worktree, refusing to "
            "mutate tracked files with no way to restore them"
        )


def _run_mutations(repo_root: Path) -> int:
    _verify_repo_root(repo_root)
    mutations = build_mutations(repo_root)
    results: list[Result] = []

    for m in mutations:
        r = apply_mutation(m, repo_root)
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


def main() -> int:
    with isolated_mutation_worktree(ACTIVE_REPO_ROOT, TARGETS) as workspace:
        return _run_mutations(workspace.root)


if __name__ == "__main__":
    sys.exit(main())
