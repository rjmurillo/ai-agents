"""Tests for ``scripts/ci/agent_review_outcome.py`` (issue #4778).

The resolver decides what a review job records when the model never ran. Two
things must hold together, and neither is sufficient alone:

* the gate blocks the merge (``DID_NOT_RUN`` is in ``BLOCKING_VERDICTS``), and
* an artifact exists at all, so ``validate_artifact_download.py`` does not exit 1
  before ``AI Quality Gate Results`` can post a readable report.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.agent_review_outcome import (
    EMPTY_VERDICT_FALLBACK,
    INFRA_SKIP_VERDICT,
    infra_ready,
    resolve_outcome,
)


def _resolve(
    verdict: str = "",
    findings: str = "",
    infrastructure_failure: str = "",
    infra_ready_value: str | None = "true",
):
    return resolve_outcome(
        verdict=verdict,
        findings=findings,
        infrastructure_failure=infrastructure_failure,
        infra_ready_value=infra_ready_value,
    )


class TestInfraReady:
    """Only the exact string 'true' clears the gate."""

    def test_the_literal_true_is_ready(self) -> None:
        assert infra_ready("true") is True

    @pytest.mark.parametrize("value", ["false", "", "True", "TRUE", "1", "yes", None])
    def test_everything_else_is_not_ready(self, value: str | None) -> None:
        assert infra_ready(value) is False


class TestRealVerdictWins:
    """A produced verdict outranks any preflight opinion."""

    def test_a_review_verdict_passes_through_untouched(self) -> None:
        outcome = _resolve(verdict="PASS", findings="looks fine")
        assert outcome.verdict == "PASS"
        assert outcome.findings == "looks fine"
        assert outcome.infrastructure_failure == ""
        assert outcome.annotations == ()

    def test_a_cached_verdict_survives_an_unavailable_preflight(self) -> None:
        # A cache hit is a real result for this commit; a dead preflight must
        # not overwrite it with DID_NOT_RUN.
        outcome = _resolve(verdict="PASS", findings="cached", infra_ready_value="false")
        assert outcome.verdict == "PASS"
        assert outcome.infrastructure_failure == ""

    def test_a_failing_verdict_is_never_downgraded_by_the_preflight(self) -> None:
        outcome = _resolve(verdict="CRITICAL_FAIL", findings="real bug", infra_ready_value="false")
        assert outcome.verdict == "CRITICAL_FAIL"

    def test_surrounding_whitespace_is_stripped(self) -> None:
        assert _resolve(verdict="  WARN  ", findings="x").verdict == "WARN"


class TestInfrastructureSkip:
    """The path the preflight opens when reviews cannot run."""

    def test_a_not_ready_preflight_records_did_not_run(self) -> None:
        outcome = _resolve(infra_ready_value="false")
        assert outcome.verdict == INFRA_SKIP_VERDICT
        assert outcome.infrastructure_failure == "true"

    def test_the_findings_explain_it_is_not_a_code_quality_judgment(self) -> None:
        outcome = _resolve(infra_ready_value="false")
        assert "did not execute" in outcome.findings
        assert "not a code-quality" in outcome.findings

    def test_the_skip_is_announced(self) -> None:
        outcome = _resolve(infra_ready_value="false")
        assert any("::warning::" in a for a in outcome.annotations)
        assert any("DID_NOT_RUN" in a for a in outcome.annotations)

    def test_a_missing_preflight_value_fails_closed(self) -> None:
        # The infra job failed, was skipped, or never published its output.
        outcome = _resolve(infra_ready_value=None)
        assert outcome.verdict == INFRA_SKIP_VERDICT
        assert outcome.infrastructure_failure == "true"

    def test_an_empty_preflight_value_fails_closed(self) -> None:
        outcome = _resolve(infra_ready_value="")
        assert outcome.verdict == INFRA_SKIP_VERDICT

    def test_existing_findings_are_preserved(self) -> None:
        outcome = _resolve(findings="partial output", infra_ready_value="false")
        assert outcome.findings == "partial output"
        assert outcome.verdict == INFRA_SKIP_VERDICT


class TestReadyButEmpty:
    """The pre-existing fallback for a review that ran and produced nothing."""

    def test_empty_verdict_with_findings_is_needs_review(self) -> None:
        outcome = _resolve(findings="some text", infra_ready_value="true")
        assert outcome.verdict == EMPTY_VERDICT_FALLBACK
        assert outcome.infrastructure_failure == ""

    def test_empty_verdict_and_findings_is_an_infrastructure_failure(self) -> None:
        outcome = _resolve(infra_ready_value="true")
        assert outcome.verdict == EMPTY_VERDICT_FALLBACK
        assert outcome.infrastructure_failure == "true"

    def test_both_empty_emits_two_annotations(self) -> None:
        outcome = _resolve(infra_ready_value="true")
        assert len(outcome.annotations) == 2

    def test_a_preexisting_infra_flag_is_preserved(self) -> None:
        outcome = _resolve(
            findings="text", infrastructure_failure="true", infra_ready_value="true"
        )
        assert outcome.infrastructure_failure == "true"


class TestFailsClosedDownstream:
    """The recorded verdict must block the merge in the canonical gate."""

    def test_the_skip_verdict_is_in_the_blocking_set(self) -> None:
        from scripts.quality_gate.check_critical_failures import BLOCKING_VERDICTS

        assert INFRA_SKIP_VERDICT in BLOCKING_VERDICTS

    def test_the_empty_fallback_is_also_in_the_blocking_set(self) -> None:
        from scripts.quality_gate.check_critical_failures import BLOCKING_VERDICTS

        assert EMPTY_VERDICT_FALLBACK in BLOCKING_VERDICTS

    def test_the_skip_verdict_matches_the_in_review_infra_gate(self) -> None:
        """Same token as the gate that fires inside a running review job."""
        from scripts.ci.check_ai_review_infra_gate import DID_NOT_RUN_VERDICT

        assert INFRA_SKIP_VERDICT == DID_NOT_RUN_VERDICT

    def test_the_skip_verdict_is_not_cached(self) -> None:
        """A DID_NOT_RUN must never poison the cache for a later run."""
        from scripts.ai_review_common.cache_guard import skip_cache_reason

        assert skip_cache_reason(INFRA_SKIP_VERDICT, "true") is not None
