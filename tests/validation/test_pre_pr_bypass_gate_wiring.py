"""pre_pr.py reaches the bypass allowlist gate, and the gate fails the run when it should.

Issue #5636, decision D17. The gate's own behavior is covered in
``test_check_bypass_allowlist.py``. This file proves the pre-PR sequence calls
it with the repository root, and that a failing result blocks (``testing.md``
SHOULD 6: prove the wiring, not only the guard).
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

from scripts.validation.evidence import CheckOutcome, pre_pr_policy

GATE_NAME = "Bypass Allowlist"


def _drive(monkeypatch: pytest.MonkeyPatch, result: CheckOutcome) -> tuple[list[str], list[Path]]:
    seen: list[Path] = []

    def spy(repo_root: Path) -> CheckOutcome:
        seen.append(repo_root)
        return result

    monkeypatch.setattr(pre_pr_sequence, "validate_bypass_allowlist", spy)
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


def _passed() -> CheckOutcome:
    return CheckOutcome.passed("validate_bypass_allowlist", revision="HEAD", scope="s", examined=1)


def test_the_sequence_emits_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    names, _ = _drive(monkeypatch, _passed())

    assert GATE_NAME in names


def test_the_gate_calls_the_validator_with_the_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    _, seen = _drive(monkeypatch, _passed())

    assert seen == [REPO_ROOT]


def test_a_failing_result_is_not_accepted_by_the_pre_pr_policy() -> None:
    """The gate is blocking: no advisory licence covers this validator."""
    failed = CheckOutcome.failed(
        "validate_bypass_allowlist", reason="violations.found", scope="s", findings=1
    )
    blocked = CheckOutcome.blocked(
        "validate_bypass_allowlist", reason="entries.unreadable", scope="s"
    )

    assert not pre_pr_policy().accepts(failed)
    assert not pre_pr_policy().accepts(blocked)
    assert pre_pr_policy().accepts(_passed())
