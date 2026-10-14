"""pre_pr.py reaches the equivalence predicates gate and passes it the repository root.

ADR-107 M1, issue #5686. The gate's own behavior is covered in
``test_check_equivalence_predicates.py``. This file proves the pre-PR sequence
calls ``validate_equivalence_predicates`` and not another validator, with the
repository root.
"""

from __future__ import annotations

import io
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import pre_pr_sequence

from scripts.validation.evidence import CheckOutcome

GATE_NAME = "Equivalence Predicates"
VALIDATOR = "equivalence_predicates"


def _drive(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[Path]]:
    seen: list[Path] = []

    def spy(repo_root: Path) -> CheckOutcome:
        seen.append(repo_root)
        return CheckOutcome.passed(VALIDATOR, revision="HEAD", scope="s", examined=1)

    monkeypatch.setattr(pre_pr_sequence, "validate_equivalence_predicates", spy)
    names: list[str] = []

    def fake_run_validation(
        name: str,
        _state: SimpleNamespace,
        callback: Callable[[], object],
        skip: bool = False,
    ) -> bool:
        names.append(name)
        if name == GATE_NAME and not skip:
            callback()
        return True

    args = SimpleNamespace(quick=False, skip_tests=False, verbose=False)
    state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
    with redirect_stdout(io.StringIO()):
        pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)
    return names, seen


def test_the_sequence_emits_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    names, _ = _drive(monkeypatch)

    assert GATE_NAME in names


def test_the_gate_calls_this_validator_with_the_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    _, seen = _drive(monkeypatch)

    assert seen == [REPO_ROOT]


def test_the_gate_is_wired_to_the_predicate_validator_not_another() -> None:
    wired = pre_pr_sequence.validate_equivalence_predicates

    assert wired.__name__ == "validate_equivalence_predicates"
    assert wired.__module__.endswith("check_equivalence_predicates")


def test_the_gate_is_not_skipped_in_quick_mode() -> None:
    gate = next(g for g in pre_pr_sequence._SEQUENCE if g.name == GATE_NAME)

    assert gate.skip_when_quick is False
