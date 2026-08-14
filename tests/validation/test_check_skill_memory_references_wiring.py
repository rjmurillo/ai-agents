"""Wiring tests for the skill memory reference pre-PR gate (issue #4897).

The checker's own behavior is covered exhaustively in
``test_check_skill_memory_references.py``. This file grades the registration
instead: a checker nobody runs cannot stop the defect it was written for. It
proves the thin wrapper in ``checks_spec.validate_skill_memory_references``
propagates every exit code (0 passes; 1 unresolved and 2 config both fail; an
absent script raises ``MissingScriptSkip`` rather than reading as clean) and
that ``pre_pr_sequence`` actually emits the gate.

Control run: deleting the ``_Gate("Skill Memory References", ...)`` row from
``pre_pr_sequence._SEQUENCE`` fails
``test_the_sequence_runs_the_gate_after_skip_clause_routing`` here plus three
order assertions in ``test_pre_pr_sequence_registry.py``, so the registration
is graded rather than assumed.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.validation import checks_spec, pre_pr_sequence
from scripts.validation.check_skill_memory_references import (
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_UNRESOLVED,
)
from scripts.validation.pre_pr import MissingScriptSkip

REPO_ROOT = Path(__file__).resolve().parents[2]

# The gate this one must run immediately after. Pinned here (and in
# EXPECTED_ORDER in test_pre_pr_sequence_registry.py) so a silent reorder that
# drops the gate out of the skill-validator cluster fails a test.
PRECEDING_GATE = "Skill SKIP Clause Routing"
GATE_NAME = "Skill Memory References"


def _stub_exit(monkeypatch: pytest.MonkeyPatch, exit_code: int, output: str) -> None:
    """Force the wrapper's subprocess to report one exit code."""
    monkeypatch.setattr(
        checks_spec,
        "_run_subprocess",
        lambda *_args, **_kwargs: (exit_code, output, ""),
    )


def test_wrapper_returns_true_on_exit_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_exit(monkeypatch, EXIT_OK, "[PASS] 0 unresolved reference(s)")

    assert checks_spec.validate_skill_memory_references(REPO_ROOT) is True


def test_wrapper_returns_false_on_unresolved_exit_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_exit(monkeypatch, EXIT_UNRESOLVED, "[FAIL] 1 unresolved reference(s)")

    assert checks_spec.validate_skill_memory_references(REPO_ROOT) is False


def test_wrapper_returns_false_on_config_exit_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit 2 is a failure too: an unmeasured corpus is not a clean corpus."""
    _stub_exit(monkeypatch, EXIT_CONFIG, "[ERROR] repo root is not a directory")

    assert checks_spec.validate_skill_memory_references(REPO_ROOT) is False


def test_wrapper_raises_when_script_absent(tmp_path: Path) -> None:
    """Vendor installs ship no validators; a skip must not read as a pass."""
    with pytest.raises(MissingScriptSkip):
        checks_spec.validate_skill_memory_references(tmp_path)


def test_the_sequence_runs_the_gate_after_skip_clause_routing() -> None:
    recorded: list[str] = []

    def fake_run_validation(
        name: str, _state: object, _callback: object, skip: bool = False
    ) -> bool:
        recorded.append(name)
        return True

    state = SimpleNamespace(total=0, skipped=0)
    args = argparse.Namespace(quick=True, skip_tests=True, verbose=False)
    pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)

    assert GATE_NAME in recorded
    assert recorded[recorded.index(PRECEDING_GATE) + 1] == GATE_NAME
