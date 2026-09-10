"""Wiring tests for the skill ADR bindings gate (issue #5665).

The gate's own behavior is covered in `test_check_skill_adr_bindings.py`. This
file proves the two things those tests structurally cannot: that `pre_pr` reaches
the gate at all, and that the adapter converts each exit code into the right
boolean.

`.claude/rules/testing.md` SHOULD 6 is the reason this file exists separately. A
guard can pass every one of its own tests while no consumer is wired to it, and
unit tests on the guard cannot observe that. Evidence cited there: a guard written
for issue #4244 passed nine mutations against its own tests while one of three
consumers never called it, and `check_skill_md_portability.py` shipped without
calling its guard while the guard's unit tests stayed green.

Per SHOULD 6 the consumer is driven twice over the same repository, differing only
in the condition the gate rejects, so a run that fails for an unrelated reason
fails its own control too.

Registration is checked in two halves, because a missing row and a misrouted row
are different defects. Both read the parsed `_SEQUENCE` tuple rather than a
substring of the module source: `testing.md` MUST 9 is explicit that a text match
passes when the row has been deleted and the name survives in a comment or a
neighbouring key. The name half asserts one row claims this gate. The behavior
half drives that row and asserts it reached THIS validator, which the name half
structurally cannot see; an earlier version of this file asserted only the name
while its docstring claimed an identity comparison, and a mutation swapping the
row's callable passed all six tests.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_skill_adr_bindings import (
    CHECK,
    EXIT_OK,
    EXIT_REGRESSION,
    main,
    validate_skill_adr_bindings,
)


def _git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run git in ``repo`` with every GIT_* variable stripped.

    The gate strips them too, through `count_ratchet.git_environment`. An
    inherited `GIT_DIR`, which `git push` exports into the pre-push hook from a
    linked worktree, would otherwise point both at the wrong index (issue #4914).
    """
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        check=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    )


def _repo_with(tmp_path: Path, *, retired_skills: int) -> Path:
    """A git repo root with one superseded ADR and ``retired_skills`` skills naming it.

    The skills are staged, not merely written: the gate enumerates candidate
    paths from the index, so an unstaged fixture would be counted as zero and
    both cases below would agree for the wrong reason.
    """
    _git(tmp_path, "init", "--quiet")
    adr_dir = tmp_path / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-002-gone.md").write_text(
        "---\nid: ADR-002\nstatus: superseded\n---\n\n# ADR-002\n", encoding="utf-8"
    )
    for index in range(retired_skills):
        skill_dir = tmp_path / "skills" / f"s{index}"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: s\nmetadata:\n  adr: ADR-002\n---\n\n# s\n", encoding="utf-8"
        )
        rel = f"skills/s{index}/SKILL.md"
        _git(tmp_path, "add", "--force", "--", rel)
        assert rel in _git(tmp_path, "ls-files", "--", rel).stdout, f"{rel} unstaged"
    return tmp_path


def _baseline(tmp_path: Path, count: int) -> Path:
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps({"schema_version": "1", "counts": {CHECK: count}}) + "\n",
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------
# Registration: the consumer reaches the gate
# --------------------------------------------------------------------------


def _registered_row():
    """The single `_SEQUENCE` row that claims to run this gate."""
    from pre_pr_sequence import _SEQUENCE

    wired = [gate for gate in _SEQUENCE if "Skill ADR Bindings" in gate.name]
    assert len(wired) == 1, f"expected exactly one row, found {len(wired)}"
    return wired[0]


def test_gate_has_exactly_one_row_in_the_pre_pr_sequence() -> None:
    """Reads the parsed `_SEQUENCE` tuple, never a substring of the module
    source, per `testing.md` MUST 9: a text match passes when the row has been
    deleted and the name survives in a comment or a neighbouring key.

    A row's NAME is not its behavior, though, which is why this is only half the
    check. `test_the_registered_row_actually_calls_this_gate` is the other half.
    """
    assert _registered_row() is not None


def test_the_registered_row_actually_calls_this_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Drives the row and proves it reached THIS validator, not merely that a
    row with this name exists.

    Measured: a mutation swapping the row's callable for `validate_adr_links`
    while leaving the name untouched passed all six wiring tests. The gate would
    never have run, and `pre_pr` would have printed a passing
    "Skill ADR Bindings (ratchet)" row for a check it never performed. Matching
    on the name alone cannot see that, and the docstring on the earlier version
    of this test claimed an identity comparison it did not make.

    `_root_only` resolves the validator by name through `globals()` at call time
    rather than capturing it at import, and its own docstring says that
    indirection exists so a wiring test can rebind the module attribute and
    observe the call. This is that test. Under the mutation the row resolves a
    different name, the rebind is never seen, and `seen` stays empty.
    """
    import pre_pr_sequence as sequence

    seen: list[Path] = []

    def _spy(repo_root: Path) -> bool:
        seen.append(repo_root)
        return True

    monkeypatch.setattr(sequence, "validate_skill_adr_bindings", _spy)
    # An initialized repository, not a bare directory. A row that resolved the
    # WRONG validator then runs that validator harmlessly and fails on the
    # assertion below, so the failure names the wiring. Against a bare tmp_path
    # the sibling ADR-links validator instead raised FileNotFoundError from its
    # own `git ls-files`, which kills the mutation but reports a subprocess crash
    # rather than the defect.
    _git(tmp_path, "init", "--quiet")
    root = tmp_path
    result = _registered_row().run(root, argparse.Namespace())

    assert seen == [root], (
        "the registered row did not call validate_skill_adr_bindings; it "
        "resolved some other validator, so this gate never runs"
    )
    assert result is True, "the row must return what this validator returned"


def test_pre_pr_facade_reexports_the_adapter() -> None:
    """The two sibling ADR gates are re-exported so
    `from scripts.validation.pre_pr import <adapter>` resolves; PR #5209 shows
    what breaks when a newly wired gate skips this line."""
    from pre_pr import validate_skill_adr_bindings as reexported

    assert reexported is validate_skill_adr_bindings


# --------------------------------------------------------------------------
# Propagation: each exit code becomes the right boolean
# --------------------------------------------------------------------------


def test_main_exits_ok_when_at_baseline(tmp_path: Path) -> None:
    """Control for the regression case below: same repo, satisfied ceiling.

    Paired with `test_main_exits_regression_above_baseline`, which differs only in
    the violation count. If this control ever fails, the discriminating test below
    proves nothing, which is the trap SHOULD 6 names.

    Renamed off "adapter": both of these drive `main` and assert an exit code,
    which is the CLI contract, not the adapter's int-to-bool conversion. Two tests
    named for the adapter never called it, so that conversion was unexercised for
    every outcome except the unrun-gate case.
    """
    repo = _repo_with(tmp_path, retired_skills=1)
    assert (
        main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, 1))])
        == EXIT_OK
    )


def test_main_exits_regression_above_baseline(tmp_path: Path) -> None:
    """The discriminating half of the pair: only the violation count differs."""
    repo = _repo_with(tmp_path, retired_skills=2)
    assert (
        main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, 1))])
        == EXIT_REGRESSION
    )


def test_adapter_is_true_when_at_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drives the adapter itself, which is what `pre_pr` calls.

    The adapter takes only a repo root, so the ceiling it reads is the module's
    `_BASELINE_PATH`. Rebinding that is the only way to reach its True and False
    branches on a fixture; without it the shipped ceiling of 16 makes every small
    fixture pass and the conversion is never discriminated.
    """
    import check_skill_adr_bindings as mod

    repo = _repo_with(tmp_path, retired_skills=1)
    monkeypatch.setattr(mod, "_BASELINE_PATH", _baseline(tmp_path, 1))
    assert validate_skill_adr_bindings(repo) is True


def test_adapter_is_false_when_above_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The discriminating half: same repo shape, one more violation."""
    import check_skill_adr_bindings as mod

    repo = _repo_with(tmp_path, retired_skills=2)
    monkeypatch.setattr(mod, "_BASELINE_PATH", _baseline(tmp_path, 1))
    assert validate_skill_adr_bindings(repo) is False


def test_adapter_is_false_on_an_unrun_gate(tmp_path: Path) -> None:
    """A gate that could not run must not be scored as a pass. `ci-scripts.md`
    MUST 11 and 12 are the reason: a config fault that returns True is
    indistinguishable from a clean tree."""
    assert validate_skill_adr_bindings(tmp_path / "no-such-repo") is False


def test_the_shipped_baseline_matches_the_tracked_tree() -> None:
    """Pins the committed ceiling against a live measurement, the same invariant
    `test_baseline_ratchet_integrity.py` holds for the other ratchets. A baseline
    that drifts above the tree leaves slack for the next regression to pass in
    silently."""
    import check_skill_adr_bindings as mod

    repo_root = Path(__file__).resolve().parents[2]
    result = mod.scan(repo_root, repo_root / ".agents" / "architecture")
    assert isinstance(result, mod.ScanResult), (
        f"scan reported a fault, so the count below would measure a string: {result!r}"
    )
    assert result.examined == result.candidates, (
        f"only {result.examined} of {result.candidates} tracked manifests were "
        f"examined, so this count is not a claim about the ref: {result.absent}"
    )
    violations = result.violations
    baseline = mod.read_baseline(mod._BASELINE_PATH)
    assert isinstance(baseline, dict), f"shipped baseline is unusable: {baseline}"
    assert baseline[CHECK] == len(violations), (
        f"shipped baseline is {baseline[CHECK]} but the tree has "
        f"{len(violations)}; lower it with --write-baseline"
    )
