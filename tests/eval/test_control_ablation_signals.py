"""Tests for the reviewer, rollback, and human-time signals of `_control_ablation.py` (issue #5768).

A signal the driver did not measure is `null` and classifies `UNVERIFIED`. These
pure tests pin that default, the recovery path decisions, and the reviewer count.
"""

from __future__ import annotations

import pytest

from tests.eval._control_ablation_test_support import (
    ablation,
    durable_outcome,
    make_evidence,
    outcome,
    review,
)


def test_build_record_defaults_unmeasured_signals_to_null_not_zero() -> None:
    record = ablation.build_record(make_evidence())

    assert record["config"]["reviewer"] == "none"
    assert record["durable"]["review_findings"] is None
    assert record["durable"]["rollback_events"] is None
    assert record["economics"]["human_correction_minutes"] is None


def test_an_evidence_with_default_signals_classifies_unverified() -> None:
    record = outcome.parse_record(ablation.build_record(make_evidence()))

    assert durable_outcome.classify(record) is durable_outcome.Verdict.UNVERIFIED


def test_build_record_carries_measured_signals_through() -> None:
    record = ablation.build_record(
        make_evidence(
            reviewer="claude:claude-sonnet-5:default",
            review_findings=2,
            rollback_events=1,
            human_correction_minutes=4.5,
        )
    )

    assert record["config"]["reviewer"] == "claude:claude-sonnet-5:default"
    assert record["durable"]["review_findings"] == 2
    assert record["durable"]["rollback_events"] == 1
    assert record["economics"]["human_correction_minutes"] == 4.5
    parsed = outcome.parse_record(record)
    assert durable_outcome.classify(parsed) is durable_outcome.Verdict.ACCEPTED_NOT_DURABLE


def test_measured_zero_signals_classify_accepted_durable() -> None:
    record = ablation.build_record(
        make_evidence(review_findings=0, rollback_events=0, human_correction_minutes=0.0)
    )

    assert (
        durable_outcome.classify(outcome.parse_record(record))
        is durable_outcome.Verdict.ACCEPTED_DURABLE
    )


# ---------------------------------------------------------------------------
# Recovery path and reviewer signal (issue #5768)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("acceptance", "followup", "expected"),
    [(0, 1, True), (0, 0, False), (1, 1, False), (1, 0, False), (0, 124, True)],
)
def test_rollback_is_needed_only_for_accepted_then_regressed(
    acceptance: int, followup: int, expected: bool
) -> None:
    assert ablation.rollback_needed(acceptance, followup) is expected


@pytest.mark.parametrize(
    ("needed", "reverted", "expected"),
    [(False, False, 0), (False, True, 0), (True, True, 1), (True, False, None)],
)
def test_rollback_events_counts_verified_reverts_and_nulls_unverified_ones(
    needed: bool, reverted: bool, expected: int | None
) -> None:
    assert ablation.rollback_events(needed, reverted) == expected


def test_review_findings_needs_an_accepted_change_and_a_well_formed_reply() -> None:
    clean = '{"findings": []}'
    two = '{"findings": ["a", "b"]}'
    marker = review.REVIEW_MARKER

    assert ablation.review_findings(0, f"{marker} {clean}") == 0
    assert ablation.review_findings(0, f"{marker} {two}") == 2
    assert ablation.review_findings(1, f"{marker} {two}") is None
    assert ablation.review_findings(0, None) is None
    assert ablation.review_findings(0, "no marker line") is None
