"""Tests for skillbook evidence math: weights, derived counts, contradict rate."""

from __future__ import annotations

import pytest

from scripts.skillbook import (
    CONTEXT_WEIGHTS,
    contradict_rate,
    evidence_weight,
    recompute_counts,
)
from tests.skillbook.conftest import make_evidence, make_policy


class TestEvidenceWeight:
    """evidence_weight maps provenance to a weight."""

    def test_external_evidence_weighted_one(self) -> None:
        assert evidence_weight(make_evidence(context_type="external")) == 1.0

    def test_self_referential_evidence_weighted_quarter(self) -> None:
        assert evidence_weight(make_evidence(context_type="self-referential")) == 0.25

    def test_unknown_context_falls_back_to_full_weight(self) -> None:
        # A missing or unrecognized context_type should not silently zero out.
        assert evidence_weight({"type": "confirmed"}) == 1.0

    def test_weight_table_has_exactly_two_contexts(self) -> None:
        assert set(CONTEXT_WEIGHTS) == {"external", "self-referential"}


class TestRecomputeCounts:
    """recompute_counts derives confirms/contradicts/application_count from evidence."""

    def test_empty_evidence_yields_zero_counts(self) -> None:
        policy = make_policy()
        recompute_counts(policy)
        assert policy["confirms"] == 0
        assert policy["contradicts"] == 0
        assert policy["application_count"] == 0

    def test_external_confirms_and_contradicts_summed(self) -> None:
        policy = make_policy(
            evidence=[
                make_evidence("confirmed", "e1"),
                make_evidence("confirmed", "e2"),
                make_evidence("contradicted", "e3"),
            ]
        )
        recompute_counts(policy)
        assert policy["confirms"] == 2.0
        assert policy["contradicts"] == 1.0
        assert policy["application_count"] == 3

    def test_self_referential_evidence_is_discounted(self) -> None:
        policy = make_policy(
            evidence=[
                make_evidence("confirmed", "e1", context_type="self-referential"),
                make_evidence("confirmed", "e2", context_type="self-referential"),
            ]
        )
        recompute_counts(policy)
        # Two self-referential confirms weigh 0.25 each.
        assert policy["confirms"] == 0.5
        assert policy["application_count"] == 2

    def test_last_tested_at_tracks_most_recent_evidence(self) -> None:
        policy = make_policy(
            evidence=[
                make_evidence("confirmed", "e1", ts=100),
                make_evidence("confirmed", "e2", ts=900),
                make_evidence("contradicted", "e3", ts=500),
            ]
        )
        recompute_counts(policy)
        assert policy["last_tested_at"] == 900


class TestContradictRate:
    """contradict_rate is contradicts / (confirms + contradicts)."""

    def test_no_evidence_is_zero_rate(self) -> None:
        assert contradict_rate(make_policy()) == 0.0

    def test_all_confirmed_is_zero_rate(self) -> None:
        assert contradict_rate(make_policy(confirms=5, contradicts=0)) == 0.0

    @pytest.mark.parametrize(
        ("confirms", "contradicts", "expected"),
        [(9, 1, 0.1), (1, 1, 0.5), (0, 3, 1.0)],
    )
    def test_rate_computed_from_counts(
        self, confirms: float, contradicts: float, expected: float
    ) -> None:
        policy = make_policy(confirms=confirms, contradicts=contradicts)
        assert contradict_rate(policy) == pytest.approx(expected)
