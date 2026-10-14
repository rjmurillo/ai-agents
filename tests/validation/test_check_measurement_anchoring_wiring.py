"""Pre-PR wiring for the measurement-anchoring gate (issue #5771).

``.claude/rules/testing.md`` SHOULD 6: prove the consumer is wired, not only
the guard. Mirrors ``test_check_citation_freshness_wiring.py``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.validation.measurement_anchoring_helpers import checker

GATE = "Measurement Anchoring (added lines)"


class TestPrePrWiring:
    def test_gate_is_registered_and_reexported_identically(self) -> None:
        from scripts.validation import pre_pr, pre_pr_sequence

        labels = [gate.name for gate in pre_pr_sequence._SEQUENCE]
        assert GATE in labels
        assert (
            pre_pr_sequence.validate_measurement_anchoring is pre_pr.validate_measurement_anchoring
        )
        assert (
            pre_pr_sequence.validate_measurement_anchoring.__code__.co_filename
            == checker.validate_measurement_anchoring.__code__.co_filename
        )

    def test_gate_verdict_reaches_the_runner(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Drive run_all_validations twice, differing only in the gate's verdict."""
        from scripts.validation import pre_pr_sequence

        repo_root = Path(__file__).resolve().parents[2]
        verdicts: dict[str, bool] = {}

        def fake_run_validation(
            name: str, _state: object, callback: object, skip: bool = False
        ) -> bool:
            if name == GATE and callable(callback):
                verdicts["gate"] = bool(callback())
            return True

        state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
        args = argparse.Namespace(quick=True, skip_tests=False, verbose=False)

        monkeypatch.setattr(pre_pr_sequence, "validate_measurement_anchoring", lambda _root: False)
        pre_pr_sequence.run_all_validations(repo_root, args, state, fake_run_validation)
        assert verdicts["gate"] is False

        monkeypatch.setattr(pre_pr_sequence, "validate_measurement_anchoring", lambda _root: True)
        pre_pr_sequence.run_all_validations(repo_root, args, state, fake_run_validation)
        assert verdicts["gate"] is True
