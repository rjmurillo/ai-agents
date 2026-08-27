#!/usr/bin/env python3
"""Mutation harness for issues #4160, #4161, #4194.

Reports three outcomes per mutation:
  DEAD         - test suite caught the mutation (expected)
  SURVIVED     - test suite passed despite the mutation (bug in tests)
  DID-NOT-APPLY - the target literal was absent; file was not mutated

A DID-NOT-APPLY exits nonzero and aborts the run. A SURVIVED also exits
nonzero. The harness also detects byte-identical files and fails if a "mutated" file
is unchanged.

One inert control (``_INERT_CONTROL``) is required to SURVIVE, per
`.claude/rules/testing.md` MUST 11: without it, a harness that fails
unconditionally reports a clean sweep. MUST 17 adds that survival alone proves
nothing, so the control is paired with a discriminating edit over the same
runner path: ``#4160 relative-parts`` mutates the same file and runs the same
suite, and must come back DEAD.

Every mutant is also exposed as a ``test_*`` function so pytest collects this
file. Before that, the file matched ``python_files`` inside ``testpaths``,
collected zero items, and exited 5, which every runner reads as success
(issue #4494).
"""

from __future__ import annotations

import filecmp
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.testing.mutation_workspace import isolated_mutation_worktree

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGETS = (
    Path("tests/ci/test_validation_scripts_are_reachable.py"),
    Path("scripts/validation/git_hook_policy.py"),
)


@dataclass(frozen=True, slots=True)
class MutationSpec:
    """One mutation: what to change, where, and which suite must catch it."""

    label: str
    target: Path
    original: str
    mutant: str
    test_paths: list[str]


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd or REPO_ROOT,
    )


def _count_occurrences(path: Path, needle: str) -> int:
    return path.read_text(encoding="utf-8").count(needle)


def _apply_mutation(path: Path, original: str, mutant: str, backup: Path) -> bool:
    """Replace ``original`` with ``mutant`` in ``path``.

    Writes a backup, applies the replacement, then uses ``cmp -s`` to assert
    the file actually changed (byte-identical file means the mutation did not
    apply). Returns True on success.
    """
    text = path.read_text(encoding="utf-8")
    if original not in text:
        return False  # DID-NOT-APPLY
    shutil.copy2(path, backup)
    mutated = text.replace(original, mutant, 1)
    path.write_text(mutated, encoding="utf-8")
    if filecmp.cmp(path, backup, shallow=False):
        shutil.copy2(backup, path)
        return False  # byte-identical: DID-NOT-APPLY
    return True


def _restore(path: Path, backup: Path) -> None:
    shutil.copy2(backup, path)
    assert filecmp.cmp(path, backup, shallow=False), (
        f"FATAL: restore of {path} is not byte-identical to backup"
    )


def _run_tests(repo_root: Path, test_paths: list[str]) -> bool:
    """Return True if the test suite passes."""
    result = _run(
        [
            sys.executable, "-m", "pytest",
            *test_paths,
            "-q", "--tb=no", "-x",
        ],
        cwd=repo_root,
    )
    return result.returncode == 0


def _mutation(
    label: str,
    target_path: Path,
    original: str,
    mutant: str,
    test_paths: list[str],
    repo_root: Path,
) -> str:
    """Apply one mutation and return 'DEAD', 'SURVIVED', or 'DID-NOT-APPLY'."""
    count = _count_occurrences(target_path, original)
    if count == 0:
        print(f"  [{label}] DID-NOT-APPLY: '{original}' not found in {target_path.name}")
        return "DID-NOT-APPLY"
    if count > 1:
        print(
            f"  [{label}] WARNING: '{original}' appears {count} times; "
            "mutating first occurrence only"
        )

    backup = target_path.with_suffix(".bak")
    applied = _apply_mutation(target_path, original, mutant, backup)
    if not applied:
        print(f"  [{label}] DID-NOT-APPLY: file unchanged after substitution")
        if backup.exists():
            backup.unlink()
        return "DID-NOT-APPLY"

    try:
        suite_passed = _run_tests(repo_root, test_paths)
    finally:
        _restore(target_path, backup)
        backup.unlink()

    if suite_passed:
        print(f"  [{label}] SURVIVED: test suite passed with mutant applied")
        return "SURVIVED"

    print(f"  [{label}] DEAD: test suite caught the mutation")
    return "DEAD"


def mutation_specs(repo_root: Path) -> list[MutationSpec]:
    """Every mutant this harness applies, rooted at ``repo_root``.

    Issue #4161's three mutations targeted
    ``.claude/skills/session-end/scripts/complete_session_log.py`` and its test
    at ``tests/skills/test_session_scripts.py``. Both were deleted with the
    session-end skill (Issue #5138); the branch-aware session-log selection
    they guarded has no surviving implementation to mutate.
    """
    # Shared by the two halves of the #4194 retro mutant: the guard line that
    # must follow the session-log lookup for the replacement to be unambiguous.
    retro_guard_tail = (
        "\n    if paths and _is_trivial_retrospective_session(session_log, paths):"
    )
    return [
        # Issue #4160: relative vs absolute path parts in skip filter
        MutationSpec(
            label="#4160 relative-parts",
            target=repo_root / "tests/ci/test_validation_scripts_are_reachable.py",
            original="p.relative_to(_REPO_ROOT).parts",
            mutant="p.parts",
            test_paths=[
                "tests/ci/test_worktree_path_filter.py",
                "tests/ci/test_validation_scripts_are_reachable.py",
            ],
        ),
        # Issue #4194: _session_log_for_current_branch in check_retrospective_evidence
        MutationSpec(
            label="#4194 retro-uses-branch-log",
            target=repo_root / "scripts/validation/git_hook_policy.py",
            original=(
                '_session_log_for_current_branch(repo_root / ".agents" / "sessions", repo_root)'
                + retro_guard_tail
            ),
            mutant=(
                '_today_session_log(repo_root / ".agents" / "sessions")' + retro_guard_tail
            ),
            test_paths=[
                "tests/validation/test_session_log_branch_aware.py",
                "tests/validation/test_git_hook_policy_causal_restore.py",
            ],
        ),
        # Issue #4194: _session_log_for_current_branch helper branch-first selection
        MutationSpec(
            label="#4194 helper-ignores-branch",
            target=repo_root / "scripts/validation/git_hook_policy.py",
            original="    return _session_log_for_branch(sessions_dir, branch)\n",
            mutant="    return _today_session_log(sessions_dir)  # mutant: ignore branch\n",
            test_paths=[
                "tests/validation/test_session_log_branch_aware.py",
            ],
        ),
    ]


MUTATION_LABELS = tuple(spec.label for spec in mutation_specs(REPO_ROOT))


def inert_control_spec(repo_root: Path) -> MutationSpec:
    """The mutation this suite must NOT catch.

    A docstring edit changes no behaviour, so the suite has to stay green. It
    runs the same file and the same suite as ``#4160 relative-parts``, which
    must come back DEAD; the pair is what makes either result readable
    (`.claude/rules/testing.md` MUST 11 and MUST 17).
    """
    return MutationSpec(
        label="inert-control docstring",
        target=repo_root / "tests/ci/test_validation_scripts_are_reachable.py",
        original='"""Every script under scripts/validation and build/scripts must have a caller.',
        mutant='"""Every script under scripts/validation and build/scripts needs a caller.',
        test_paths=["tests/ci/test_validation_scripts_are_reachable.py"],
    )


def run_spec(spec: MutationSpec, repo_root: Path) -> str:
    """Apply one spec inside ``repo_root`` and return its outcome string."""
    return _mutation(
        spec.label,
        spec.target,
        spec.original,
        spec.mutant,
        spec.test_paths,
        repo_root,
    )


def _run_mutations(repo_root: Path) -> int:
    specs = mutation_specs(repo_root)
    results: dict[str, list[str]] = {"DEAD": [], "SURVIVED": [], "DID-NOT-APPLY": []}

    print("=" * 60)
    print("Mutation harness: worktree path resolution fixes")
    print("=" * 60)

    for spec in specs:
        print(f"\nMutation: {spec.label}")
        results[run_spec(spec, repo_root)].append(spec.label)

    control = inert_control_spec(repo_root)
    print(f"\nInert control: {control.label}")
    control_outcome = run_spec(control, repo_root)

    print("\n" + "=" * 60)
    print("Results:")
    for outcome, labels in results.items():
        for label in labels:
            print(f"  {outcome:16s} {label}")
    print(f"  {control_outcome:16s} {control.label} (must be SURVIVED)")

    dead = len(results["DEAD"])
    survived = len(results["SURVIVED"])
    did_not_apply = len(results["DID-NOT-APPLY"])

    print(
        f"\nSummary: {len(specs)} mutants applied, {dead} DEAD, {survived} SURVIVED, "
        f"{did_not_apply} DID-NOT-APPLY, control {control_outcome}"
    )

    if survived:
        print("FAIL: surviving mutants indicate missing test coverage", file=sys.stderr)
        return 1
    if did_not_apply:
        print(
            "FAIL: DID-NOT-APPLY mutations indicate the target literal has changed; "
            "update the harness",
            file=sys.stderr,
        )
        return 1
    if control_outcome != "SURVIVED":
        print(
            f"FAIL: inert control reported {control_outcome}; the harness fails "
            "regardless of the mutant, so the kills above prove nothing",
            file=sys.stderr,
        )
        return 1

    print(f"PASS: all {dead} mutants killed; inert control survived")
    return 0


def main() -> int:
    with isolated_mutation_worktree(REPO_ROOT, TARGETS) as workspace:
        return _run_mutations(workspace.root)


if __name__ == "__main__":
    sys.exit(main())


@pytest.fixture()
def mutation_repo() -> Iterator[Path]:
    """Yield a disposable worktree so no mutation touches the active checkout."""
    with isolated_mutation_worktree(REPO_ROOT, TARGETS) as workspace:
        yield workspace.root


@pytest.mark.parametrize("label", MUTATION_LABELS)
def test_mutant_is_dead(label: str, mutation_repo: Path) -> None:
    """Each mutant must be caught by the suite named in its spec."""
    spec = next(s for s in mutation_specs(mutation_repo) if s.label == label)

    outcome = run_spec(spec, mutation_repo)

    assert outcome == "DEAD", f"{label}: expected DEAD, got {outcome}"


def test_inert_control_survives(mutation_repo: Path) -> None:
    """A docstring edit must not be caught, or every kill above is unreadable."""
    outcome = run_spec(inert_control_spec(mutation_repo), mutation_repo)

    assert outcome == "SURVIVED", (
        f"inert control reported {outcome}; the suite fails regardless of the "
        "mutant, so the DEAD results prove nothing"
    )
