"""Wiring test for the index-line-endings gate in the pre-PR runner (#5475).

The gate's own unit tests prove the gate. They cannot prove any call site
reached it (`.claude/rules/testing.md` SHOULD 6), and the sequence registry
test pins only the label and its position: `_record`'s fake runner never
invokes the callback, so `Index Line Endings` could be wired to a different
validator and that test would still pass.

These drive the real sequence, so a gate removed from `_SEQUENCE` or pointed
at the wrong validator fails here.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way the runner does; see test_pre_pr_worktree_gate_wiring.py for
# why sys.path is inserted once and deliberately never restored.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_index_line_endings
import pre_pr_sequence

GATE = "Index Line Endings"


class _State:
    """Minimal stand-in for pre_pr.ValidationState."""

    def __init__(self) -> None:
        self.total = 0
        self.skipped = 0


def _run_sequence(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """Drive the real sequence, filtered to this gate, and return its verdict."""
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

    # Filtering the real _SEQUENCE, rather than building a fake one, is what
    # makes this a wiring test: removing the gate empties the filter and the
    # assertions below fail.
    wanted = [gate for gate in pre_pr_sequence._SEQUENCE if gate.name == GATE]
    monkeypatch.setattr(pre_pr_sequence, "_SEQUENCE", tuple(wanted))

    args = argparse.Namespace(quick=False, skip_tests=False, verbose=False)
    pre_pr_sequence.run_all_validations(REPO_ROOT, args, _State(), record)
    return verdicts


def test_the_gate_is_registered_in_the_sequence() -> None:
    assert GATE in [gate.name for gate in pre_pr_sequence._SEQUENCE]


def test_the_sequence_runs_the_gate_and_it_passes_on_the_real_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _run_sequence(monkeypatch) == {GATE: True}


def test_the_gate_fails_the_sequence_when_a_blob_contradicts_its_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative control: the same run that passed above, with one bad blob.

    Rebinding `check_index_line_endings.check_repository` is the discriminator.
    If the row were wired to some other validator, this stub would never be
    consulted and the verdict would stay True.
    """
    bad = check_index_line_endings.Violation(
        path="docs/x.md",
        index_state="i/crlf",
        attributes="attr/text eol=lf",
        scope="HEAD",
    )
    monkeypatch.setattr(
        check_index_line_endings,
        "check_repository",
        lambda _root: ([bad], 1),
    )

    verdicts = _run_sequence(monkeypatch)

    assert verdicts[GATE] is False, "pre_pr is not wired to the line-ending checker"


def test_the_gate_receives_the_repository_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The row must pass the repo root through, not some other path."""
    seen: list[Path] = []

    def _spy(root: Path) -> tuple[list[object], int]:
        seen.append(root)
        return ([], 1)

    monkeypatch.setattr(check_index_line_endings, "check_repository", _spy)

    _run_sequence(monkeypatch)

    assert seen == [REPO_ROOT]
