"""Pre-PR wiring for the citation gate (issue #5337).

Split from ``test_check_citation_freshness_scope.py`` at the taste
file-size ceiling, along the class seam: this file proves the consumer
is wired (testing.md SHOULD 6), the scope file proves the gate itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.citation_freshness_helpers import checker


class TestPrePrWiring:
    """testing.md SHOULD 6: prove the consumer is wired, not only the guard."""

    def test_gate_is_registered_and_reexported_identically(self) -> None:
        from scripts.validation import pre_pr, pre_pr_sequence

        labels = [gate.name for gate in pre_pr_sequence._SEQUENCE]
        assert "Citation Freshness (added lines)" in labels
        # Identity is asserted between the two flat-imported modules (the
        # registry promise); ``checker`` here is the package-imported module,
        # a distinct module object for the same file, so it is compared by
        # source file rather than by function identity.
        assert pre_pr_sequence.validate_citation_freshness is pre_pr.validate_citation_freshness
        assert (
            pre_pr_sequence.validate_citation_freshness.__code__.co_filename
            == checker.validate_citation_freshness.__code__.co_filename
        )

    def test_gate_verdict_reaches_the_runner(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Drive run_all_validations twice, differing only in the gate's verdict.

        A registration-only assertion passes even when the callback is
        replaced with an always-true stub (Copilot, PR #5338); calling the
        real runner with a monkeypatched validator proves the by-name
        resolution in _root_only actually reaches this gate's verdict, with
        the passing run as the control.
        """
        import argparse
        from types import SimpleNamespace

        from scripts.validation import pre_pr_sequence

        repo_root = Path(__file__).resolve().parents[2]
        verdicts: dict[str, bool] = {}

        def fake_run_validation(
            name: str, _state: object, callback: object, skip: bool = False
        ) -> bool:
            if name == "Citation Freshness (added lines)" and callable(callback):
                verdicts["gate"] = bool(callback())
            return True

        state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
        args = argparse.Namespace(quick=True, skip_tests=False, verbose=False)

        monkeypatch.setattr(pre_pr_sequence, "validate_citation_freshness", lambda _root: False)
        pre_pr_sequence.run_all_validations(repo_root, args, state, fake_run_validation)
        assert verdicts["gate"] is False

        monkeypatch.setattr(pre_pr_sequence, "validate_citation_freshness", lambda _root: True)
        pre_pr_sequence.run_all_validations(repo_root, args, state, fake_run_validation)
        assert verdicts["gate"] is True
