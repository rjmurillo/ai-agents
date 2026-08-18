"""Wiring tests for the two worktree gates in the pre-PR runner (issue #5111).

A gate's own unit tests prove the gate. They cannot prove any call site reached
it, so a gate can pass every test it owns while `pre_pr` never calls it
(`.claude/rules/testing.md` SHOULD 6). These tests drive the real sequence and
fail when either gate is unwired.

Both gates are driven over the same input twice, differing only in the
condition the gate rejects, so a run that fails for an unrelated reason fails
its own control too.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way the runner does. See the header of
# tests/validation/test_pre_pr_model_pin_wiring.py for why sys.path is inserted
# once and deliberately never restored.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_tmp_worktrees
import check_worktree_recipes
import pre_pr_sequence

RECIPE_GATE = "Worktree Recipe Destinations"
TEMP_GATE = "Temp-filesystem Worktrees (advisory)"


class _State:
    """Minimal stand-in for pre_pr.ValidationState."""

    def __init__(self) -> None:
        self.total = 0
        self.skipped = 0


def _run_sequence(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """Drive the real sequence and return each gate's verdict by name."""
    verdicts: dict[str, bool] = {}

    def record(
        name: str,
        state: _State,
        callback: Callable[[], bool],
        skip: bool = False,
    ) -> bool:
        state.total += 1
        if skip:
            state.skipped += 1
            return True
        result = bool(callback())
        verdicts[name] = result
        return result

    # Every other gate is expensive and irrelevant here, so run only the two
    # under test. Filtering the real _SEQUENCE (rather than building a fake one)
    # is what keeps this a wiring test: a gate removed from _SEQUENCE
    # disappears from the filter and the assertions below fail.
    wanted = [gate for gate in pre_pr_sequence._SEQUENCE if gate.name in (RECIPE_GATE, TEMP_GATE)]
    monkeypatch.setattr(pre_pr_sequence, "_SEQUENCE", tuple(wanted))

    args = argparse.Namespace(quick=False, skip_tests=False, verbose=False)
    pre_pr_sequence.run_all_validations(REPO_ROOT, args, _State(), record)
    return verdicts


def test_both_worktree_gates_are_registered_in_the_sequence() -> None:
    names = [gate.name for gate in pre_pr_sequence._SEQUENCE]

    assert RECIPE_GATE in names
    assert TEMP_GATE in names


def test_the_sequence_runs_both_gates_and_they_pass_on_the_real_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verdicts = _run_sequence(monkeypatch)

    assert verdicts == {RECIPE_GATE: True, TEMP_GATE: True}


def test_the_recipe_gate_fails_the_sequence_when_a_prescription_is_bad(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative control for the same run that passed above."""
    bad = check_worktree_recipes.Violation(
        path="docs/x.md",
        line_number=1,
        destination="/tmp/wt",
        reason=check_worktree_recipes.REASON_TEMP,
    )
    monkeypatch.setattr(
        check_worktree_recipes,
        "check_repository",
        lambda _root: ([bad], 1),
    )

    verdicts = _run_sequence(monkeypatch)

    assert verdicts[RECIPE_GATE] is False, "pre_pr is not wired to the recipe checker"
    assert verdicts[TEMP_GATE] is True, "the advisory gate must be unaffected"


def test_the_temp_gate_stays_advisory_inside_the_sequence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The advisory gate reports a finding through the sequence without failing it."""
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    monkeypatch.setattr(check_tmp_worktrees, "DEFAULT_TEMP_ROOT", tmp_path)

    verdicts = _run_sequence(monkeypatch)

    assert verdicts[TEMP_GATE] is True
