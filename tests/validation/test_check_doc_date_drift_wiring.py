"""Pre-PR wiring for the doc-date-drift gate (PRs #7428 and #6925).

``rule-testing.md`` SHOULD 6: prove the consumer is wired, not only
the guard. Mirrors ``test_check_measurement_anchoring_wiring.py``, except the
verdict is a typed ``CheckOutcome`` because this gate is advisory.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.validation import check_doc_date_drift as checker
from scripts.validation.evidence import CheckOutcome, coerce_outcome, pre_pr_policy

GATE = "Doc Date Drift (advisory, added lines)"


class TestPrePrWiring:
    def test_gate_is_registered_after_measurement_anchoring(self) -> None:
        from scripts.validation import pre_pr_sequence

        labels = [gate.name for gate in pre_pr_sequence._SEQUENCE]
        assert GATE in labels
        assert labels.index(GATE) == labels.index("Measurement Anchoring (added lines)") + 1

    def test_gate_is_reexported_identically(self) -> None:
        from scripts.validation import pre_pr, pre_pr_sequence

        assert pre_pr_sequence.validate_doc_date_drift is pre_pr.validate_doc_date_drift
        assert (
            pre_pr_sequence.validate_doc_date_drift.__code__.co_filename
            == checker.validate_doc_date_drift.__code__.co_filename
        )

    def test_gate_verdict_reaches_the_runner_without_blocking(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drive the real sequence twice: a warning must not block, a hard failure must."""
        from scripts.validation import pre_pr_sequence

        repo_root = Path(__file__).resolve().parents[2]
        verdicts: dict[str, object] = {}

        def record(name: str, state: object, callback: object, skip: bool = False) -> bool:
            if name == GATE and callable(callback):
                outcome = coerce_outcome(name, callback())
                verdicts["accepted"] = pre_pr_policy().accepts(outcome)
                verdicts["state"] = outcome.state.value
            return True

        wanted = tuple(g for g in pre_pr_sequence._SEQUENCE if g.name == GATE)
        monkeypatch.setattr(pre_pr_sequence, "_SEQUENCE", wanted)
        args = argparse.Namespace(quick=False, skip_tests=False, verbose=False)
        state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)

        warning = CheckOutcome.failed(
            "validate_doc_date_drift",
            reason="advisory.findings",
            revision="HEAD",
            scope="added lines",
            findings=1,
        )
        monkeypatch.setattr(pre_pr_sequence, "validate_doc_date_drift", lambda _root: warning)
        pre_pr_sequence.run_all_validations(repo_root, args, state, record)
        assert verdicts["accepted"] is True
        assert verdicts["state"] != "PASS"

        unlicensed = CheckOutcome.failed(
            "validate_doc_date_drift", reason="violations.found", findings=1
        )
        monkeypatch.setattr(pre_pr_sequence, "validate_doc_date_drift", lambda _root: unlicensed)
        pre_pr_sequence.run_all_validations(repo_root, args, state, record)
        assert verdicts["accepted"] is False
