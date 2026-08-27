#!/usr/bin/env python3
"""Mutation harness for issues #4160 and #4194.

Reports four outcomes per mutation:
  DEAD          - the suite named in the spec caught the mutation (expected)
  SURVIVED      - the suite passed despite the mutation (bug in tests)
  DID-NOT-APPLY - the target literal was absent; the file was not mutated
  HARNESS-ERROR - pytest ran no tests, so the run graded nothing

Only DEAD and SURVIVED are results about the code. The other two are results
about the harness, and each spec carries the outcome it requires in
``MutationSpec.expected`` so a reader never has to remember which polarity
applies to which label.

Controls, one per runner path
-----------------------------

`.claude/rules/testing.md` MUST 11 requires an inverted control: a mutation the
suite must SURVIVE, without which a harness that fails unconditionally reports a
clean sweep. MUST 17 adds that survival alone proves nothing, so each control is
paired with a discriminating edit that must be DEAD.

A control only observes the suite it runs. The control shipped before this
revision mutated ``tests/ci/test_validation_scripts_are_reachable.py`` and ran
only that one file, so it could not see breakage in the two
``tests/validation/`` suites the #4194 mutants depend on: with an
unconditionally-failing test appended to
``tests/validation/test_session_log_branch_aware.py``, both #4194 mutants
reported DEAD and the control still reported SURVIVED.

``controls()`` therefore returns one control per distinct runner path, each
running byte-for-byte the same ``test_paths`` as the mutants it vouches for, and
``test_every_runner_path_has_an_inert_control`` fails by name on any runner path
that gains a mutant without gaining a control.

Every mutant and every control is also exposed as a ``test_*`` function so
pytest collects this file. Before that, the file matched ``python_files`` inside
``testpaths``, collected zero items, and exited 5, which every runner reads as
success (issue #4494).
"""

from __future__ import annotations

import filecmp
import shutil
import subprocess
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from scripts.testing.mutation_workspace import isolated_mutation_worktree

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGETS = (
    Path("tests/ci/test_validation_scripts_are_reachable.py"),
    Path("scripts/validation/git_hook_policy.py"),
)

DEAD = "DEAD"
SURVIVED = "SURVIVED"
DID_NOT_APPLY = "DID-NOT-APPLY"
HARNESS_ERROR_PREFIX = "HARNESS-ERROR"

# One runner path per suite invocation. A mutant and the control that vouches
# for it must name the identical list, so they are declared once here.
CI_RUNNER_PATH = (
    "tests/ci/test_worktree_path_filter.py",
    "tests/ci/test_validation_scripts_are_reachable.py",
)
RETRO_RUNNER_PATH = (
    "tests/validation/test_session_log_branch_aware.py",
    "tests/validation/test_git_hook_policy_causal_restore.py",
)
BRANCH_AWARE_RUNNER_PATH = ("tests/validation/test_session_log_branch_aware.py",)


@dataclass(frozen=True, slots=True)
class MutationSpec:
    """One mutation: what to change, which suite runs, and what must come back."""

    label: str
    target: Path
    original: str
    mutant: str
    test_paths: list[str]
    expected: str


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

    Writes a backup, applies the replacement, then compares the bytes to assert
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


def _run_tests(
    repo_root: Path, test_paths: Sequence[str]
) -> subprocess.CompletedProcess[str]:
    """Run the spec's suite by filesystem path and return the finished process."""
    return _run(
        [
            sys.executable, "-m", "pytest",
            *test_paths,
            "-q", "--tb=no", "-x",
        ],
        cwd=repo_root,
    )


def _classify(proc: subprocess.CompletedProcess[str]) -> str:
    """Grade one pytest run, rejecting the runner's silent-nothing-ran signals.

    `.claude/rules/testing.md` MUST 11 requires that a harness shelling out to a
    test runner "reject the runner's silent-nothing-ran signals directly, at
    minimum ``"no tests ran"`` absent from the output and a ``returncode`` that
    is not pytest's usage-error 4". Grading every non-zero exit as DEAD reports a
    kill for a spec whose ``test_paths`` no longer exist, having run zero tests.

    Mirrors ``_classify`` in the sibling harness
    ``tests/mutation/test_mutate_baseline_ratchet_integrity.py``, quoted verbatim
    from its lines 58 to 65::

        def _classify(proc: subprocess.CompletedProcess[str]) -> str:
            if proc.returncode == 4:
                return "HARNESS-ERROR: pytest exit 4 (no tests ran via path)"
            if "no tests ran" in proc.stdout.lower() or "no tests ran" in proc.stderr.lower():
                return "HARNESS-ERROR: no tests ran"
            if proc.returncode == 0:
                return "SURVIVED"
            return "DEAD"

    Stricter than the sibling: this adds pytest's exit 5 (nothing collected) as a
    third harness error. The sibling runs one fixed test file and would read a 5
    as DEAD; these specs name several paths each, so a path that stops collecting
    is the failure this harness has to see.
    """
    if proc.returncode == 4:
        return f"{HARNESS_ERROR_PREFIX}: pytest exit 4 (no tests ran via path)"
    if proc.returncode == 5:
        return f"{HARNESS_ERROR_PREFIX}: no tests collected"
    if "no tests ran" in proc.stdout.lower() or "no tests ran" in proc.stderr.lower():
        return f"{HARNESS_ERROR_PREFIX}: no tests ran"
    if proc.returncode == 0:
        return SURVIVED
    return DEAD


def _mutation(spec: MutationSpec, repo_root: Path) -> str:
    """Apply one spec and return its outcome string."""
    target_path = spec.target
    count = _count_occurrences(target_path, spec.original)
    if count == 0:
        print(
            f"  [{spec.label}] {DID_NOT_APPLY}: "
            f"'{spec.original}' not found in {target_path.name}"
        )
        return DID_NOT_APPLY
    if count > 1:
        print(
            f"  [{spec.label}] WARNING: '{spec.original}' appears {count} times; "
            "mutating first occurrence only"
        )

    backup = target_path.with_suffix(".bak")
    applied = _apply_mutation(target_path, spec.original, spec.mutant, backup)
    if not applied:
        print(f"  [{spec.label}] {DID_NOT_APPLY}: file unchanged after substitution")
        if backup.exists():
            backup.unlink()
        return DID_NOT_APPLY

    try:
        outcome = _classify(_run_tests(repo_root, spec.test_paths))
    finally:
        _restore(target_path, backup)
        backup.unlink()

    print(f"  [{spec.label}] {outcome} (expected {spec.expected})")
    return outcome


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
            test_paths=list(CI_RUNNER_PATH),
            expected=DEAD,
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
            test_paths=list(RETRO_RUNNER_PATH),
            expected=DEAD,
        ),
        # Issue #4194: _session_log_for_current_branch helper branch-first selection
        MutationSpec(
            label="#4194 helper-ignores-branch",
            target=repo_root / "scripts/validation/git_hook_policy.py",
            original="    return _session_log_for_branch(sessions_dir, branch)\n",
            mutant="    return _today_session_log(sessions_dir)  # mutant: ignore branch\n",
            test_paths=list(BRANCH_AWARE_RUNNER_PATH),
            expected=DEAD,
        ),
    ]


def controls(repo_root: Path) -> list[MutationSpec]:
    """One inert control per runner path used by ``mutation_specs``.

    A docstring edit changes no behaviour, so the suite has to stay green. Each
    control runs byte-for-byte the same ``test_paths`` as the mutants it vouches
    for, because a control can only observe the suite it actually runs.
    """
    ci_docstring = (
        '"""Every script under scripts/validation and build/scripts must have a caller.'
    )
    ci_docstring_mutant = (
        '"""Every script under scripts/validation and build/scripts needs a caller.'
    )
    policy_docstring = (
        '"""Narrow Git policies that Lefthook cannot express declaratively."""'
    )
    policy_docstring_mutant = (
        '"""Narrow Git policies Lefthook cannot express declaratively."""'
    )
    return [
        MutationSpec(
            label="inert-control ci-runner-path",
            target=repo_root / "tests/ci/test_validation_scripts_are_reachable.py",
            original=ci_docstring,
            mutant=ci_docstring_mutant,
            test_paths=list(CI_RUNNER_PATH),
            expected=SURVIVED,
        ),
        MutationSpec(
            label="inert-control retro-runner-path",
            target=repo_root / "scripts/validation/git_hook_policy.py",
            original=policy_docstring,
            mutant=policy_docstring_mutant,
            test_paths=list(RETRO_RUNNER_PATH),
            expected=SURVIVED,
        ),
        MutationSpec(
            label="inert-control branch-aware-runner-path",
            target=repo_root / "scripts/validation/git_hook_policy.py",
            original=policy_docstring,
            mutant=policy_docstring_mutant,
            test_paths=list(BRANCH_AWARE_RUNNER_PATH),
            expected=SURVIVED,
        ),
    ]


MUTATION_LABELS = tuple(spec.label for spec in mutation_specs(REPO_ROOT))
CONTROL_LABELS = tuple(spec.label for spec in controls(REPO_ROOT))


def run_spec(spec: MutationSpec, repo_root: Path) -> str:
    """Apply one spec inside ``repo_root`` and return its outcome string."""
    return _mutation(spec, repo_root)


def _spec_named(specs: list[MutationSpec], label: str) -> MutationSpec:
    """Look a spec up by label, failing readably when the label has drifted.

    ``MUTATION_LABELS`` and ``CONTROL_LABELS`` are built from ``REPO_ROOT`` at
    import, while the spec that runs is built from the disposable worktree. A
    label present in one and absent from the other used to surface as a bare
    ``StopIteration`` from ``next()``, which names neither the label nor the two
    sources that disagree.
    """
    by_label = {spec.label: spec for spec in specs}
    if label not in by_label:
        raise AssertionError(
            f"no spec named {label} in the worktree copy; "
            f"worktree labels are {sorted(by_label)}"
        )
    return by_label[label]


@pytest.fixture()
def mutation_repo() -> Iterator[Path]:
    """Yield a disposable worktree so no mutation touches the active checkout."""
    with isolated_mutation_worktree(REPO_ROOT, TARGETS) as workspace:
        yield workspace.root


@pytest.mark.parametrize("label", MUTATION_LABELS)
def test_mutant_is_dead(label: str, mutation_repo: Path) -> None:
    """Each mutant must be caught by the suite named in its spec."""
    spec = _spec_named(mutation_specs(mutation_repo), label)

    outcome = run_spec(spec, mutation_repo)

    assert outcome == DEAD, f"{label}: expected {DEAD}, got {outcome}"


@pytest.mark.parametrize("label", CONTROL_LABELS)
def test_inert_control_survives(label: str, mutation_repo: Path) -> None:
    """A docstring edit must not be caught, or every kill above is unreadable."""
    spec = _spec_named(controls(mutation_repo), label)

    outcome = run_spec(spec, mutation_repo)

    assert outcome == SURVIVED, (
        f"{label} reported {outcome}; the suite it runs "
        f"({', '.join(spec.test_paths)}) fails regardless of the mutant, so the "
        f"{DEAD} results over that same suite prove nothing"
    )


def test_every_runner_path_has_an_inert_control() -> None:
    """A mutant whose runner path has no control is graded by an unread gauge.

    The control that shipped with issue #4494 ran only
    ``tests/ci/test_validation_scripts_are_reachable.py``, so the two #4194
    mutants over ``tests/validation/`` had no control at all and a broken suite
    there read as a clean sweep.
    """
    control_paths = {tuple(spec.test_paths) for spec in controls(REPO_ROOT)}

    uncovered = {
        spec.label: tuple(spec.test_paths)
        for spec in mutation_specs(REPO_ROOT)
        if tuple(spec.test_paths) not in control_paths
    }

    assert not uncovered, (
        "every runner path in mutation_specs needs an inert control running the "
        f"identical test_paths; uncovered: {uncovered}"
    )


def test_every_control_is_declared_as_an_inverted_control() -> None:
    """``expected`` is the field a reader trusts, so it must match the polarity."""
    assert [spec.expected for spec in controls(REPO_ROOT)] == [SURVIVED] * len(
        CONTROL_LABELS
    )
    assert [spec.expected for spec in mutation_specs(REPO_ROOT)] == [DEAD] * len(
        MUTATION_LABELS
    )


def _completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["pytest"], returncode=returncode, stdout=stdout, stderr=stderr
    )


_EXIT_4 = f"{HARNESS_ERROR_PREFIX}: pytest exit 4 (no tests ran via path)"
_EXIT_5 = f"{HARNESS_ERROR_PREFIX}: no tests collected"
_NOTHING_RAN = f"{HARNESS_ERROR_PREFIX}: no tests ran"


@pytest.mark.parametrize(
    ("proc", "expected"),
    [
        (_completed(0, "3 passed in 0.1s"), SURVIVED),
        (_completed(1, "1 failed, 2 passed in 0.1s"), DEAD),
        (_completed(2, "INTERNALERROR"), DEAD),
        (_completed(4, "ERROR: file or directory not found"), _EXIT_4),
        (_completed(5, "no tests ran in 0.01s"), _EXIT_5),
        (_completed(1, "NO TESTS RAN"), _NOTHING_RAN),
        (_completed(1, "", "no tests ran"), _NOTHING_RAN),
    ],
)
def test_classify_grades_each_runner_signal(
    proc: subprocess.CompletedProcess[str], expected: str
) -> None:
    """A non-zero exit is only a kill when tests actually ran (MUST 11)."""
    assert _classify(proc) == expected


def test_a_spec_naming_a_missing_test_file_is_not_graded_dead(
    mutation_repo: Path,
) -> None:
    """A spec whose suite has moved must report a harness error, never a kill.

    Before ``_classify``, ``_run_tests`` returned ``result.returncode == 0`` and
    every non-zero exit became DEAD, so pointing a spec at a path that does not
    exist reported a kill having collected nothing.
    """
    spec = replace(
        _spec_named(mutation_specs(mutation_repo), "#4160 relative-parts"),
        label="missing-test-path probe",
        test_paths=["tests/validation/test_this_file_does_not_exist.py"],
    )

    outcome = run_spec(spec, mutation_repo)

    assert outcome != DEAD, "a run that collected no tests reported a kill"
    assert outcome.startswith(HARNESS_ERROR_PREFIX), (
        f"expected a {HARNESS_ERROR_PREFIX} outcome, got {outcome}"
    )
