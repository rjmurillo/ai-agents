"""Pre-PR wiring for the io-portability gate.

``.claude/rules/testing.md`` SHOULD 6: prove the consumer is wired, not only
the guard. Mirrors ``test_check_measurement_anchoring_wiring.py``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from scripts.validation import check_io_portability as checker

GATE = "IO Portability (added lines)"


class TestPrePrWiring:
    def test_gate_is_registered_and_reexported_identically(self) -> None:
        from scripts.validation import pre_pr, pre_pr_sequence

        labels = [gate.name for gate in pre_pr_sequence._SEQUENCE]
        assert GATE in labels
        assert pre_pr_sequence.validate_io_portability is pre_pr.validate_io_portability
        assert (
            pre_pr_sequence.validate_io_portability.__code__.co_filename
            == checker.validate_io_portability.__code__.co_filename
        )

    @pytest.mark.parametrize("fast_stage_ran", [None, "1"])
    def test_gate_verdict_reaches_the_runner(
        self, monkeypatch: pytest.MonkeyPatch, fast_stage_ran: str | None
    ) -> None:
        """Drive run_all_validations twice, differing only in the gate's verdict.

        A pre-push run sets the fast-stage variable, which skips other gates
        through ``state.hides`` and ``state.record``; the gate must still run.
        """
        from scripts.validation import pre_pr_sequence
        from scripts.validation.pre_pr_state import ValidationState

        if fast_stage_ran is None:
            monkeypatch.delenv(pre_pr_sequence.FAST_STAGE_RAN_ENV, raising=False)
        else:
            monkeypatch.setenv(pre_pr_sequence.FAST_STAGE_RAN_ENV, fast_stage_ran)

        repo_root = Path(__file__).resolve().parents[2]
        verdicts: dict[str, bool] = {}

        def fake_run_validation(
            name: str, _state: object, callback: object, skip: bool = False
        ) -> bool:
            if name == GATE and callable(callback):
                verdicts["gate"] = bool(callback())
            return True

        state = ValidationState()
        args = argparse.Namespace(quick=True, skip_tests=False, verbose=False)

        monkeypatch.setattr(pre_pr_sequence, "validate_io_portability", lambda _root: False)
        pre_pr_sequence.run_all_validations(repo_root, args, state, fake_run_validation)
        assert verdicts["gate"] is False

        monkeypatch.setattr(pre_pr_sequence, "validate_io_portability", lambda _root: True)
        pre_pr_sequence.run_all_validations(repo_root, args, state, fake_run_validation)
        assert verdicts["gate"] is True
