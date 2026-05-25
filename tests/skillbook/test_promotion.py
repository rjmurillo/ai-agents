"""Tests for skillbook tier promotion, status flips, and the never-decrease rule.

The acceptance criteria for issue #2030 call out two invariants explicitly:
  - Tiers never decrease.
  - A validated policy whose contradict rate rises flips status to
    'questioning' rather than demoting its tier.
Both are exercised here, including the documented boundary case.
"""

from __future__ import annotations

import pytest

from scripts.skillbook import (
    TIER_RANK,
    add_evidence,
    eligible_tier,
    make_evidence_entry,
    promote_policy,
    resolve_status,
    run_promote,
)
from tests.skillbook.conftest import make_evidence, make_policy


def _confirmed(eval_id: str, ts: int = 1000) -> dict:
    """Build a confirmed external evidence entry."""
    return make_evidence_entry(
        evidence_type="confirmed",
        eval_id=eval_id,
        context_type="external",
        ts=ts,
    )


def _contradicted(eval_id: str, ts: int = 2000) -> dict:
    """Build a contradicted external evidence entry."""
    return make_evidence_entry(
        evidence_type="contradicted",
        eval_id=eval_id,
        context_type="external",
        ts=ts,
    )


class TestEligibleTier:
    """eligible_tier reports the tier the evidence currently qualifies for."""

    def test_no_evidence_is_hypothesis(self) -> None:
        assert eligible_tier(make_policy()) == "hypothesis"

    def test_one_confirm_is_observed(self) -> None:
        assert eligible_tier(make_policy(confirms=1, contradicts=0)) == "observed"

    def test_five_confirms_no_contradicts_is_validated(self) -> None:
        assert eligible_tier(make_policy(confirms=5, contradicts=0)) == "validated"

    def test_four_confirms_is_only_observed(self) -> None:
        assert eligible_tier(make_policy(confirms=4, contradicts=0)) == "observed"

    def test_rate_exactly_ten_percent_is_validated(self) -> None:
        # 9 confirms + 1 contradict = 10% contradict rate, at the gate.
        assert eligible_tier(make_policy(confirms=9, contradicts=1)) == "validated"

    def test_rate_just_over_ten_percent_is_not_validated(self) -> None:
        # 8 confirms + 2 contradicts = 20% contradict rate.
        assert eligible_tier(make_policy(confirms=8, contradicts=2)) == "observed"


class TestResolveStatus:
    """resolve_status decides active / questioning / retired."""

    def test_observed_policy_is_active(self) -> None:
        policy = make_policy(confirms=2, contradicts=0)
        assert resolve_status(policy, "observed") == "active"

    def test_validated_within_gate_is_active(self) -> None:
        policy = make_policy(confirms=9, contradicts=1)
        assert resolve_status(policy, "validated") == "active"

    def test_validated_over_gate_is_questioning(self) -> None:
        policy = make_policy(confirms=9, contradicts=3)
        assert resolve_status(policy, "validated") == "questioning"

    def test_retired_policy_stays_retired(self) -> None:
        policy = make_policy(status="retired", confirms=9, contradicts=9)
        assert resolve_status(policy, "validated") == "retired"


class TestPromotePolicy:
    """promote_policy applies the tier and status, never decreasing the tier."""

    def test_hypothesis_promotes_to_observed(self) -> None:
        policy = make_policy(tier="hypothesis", confirms=1, contradicts=0)
        assert promote_policy(policy) is True
        assert policy["tier"] == "observed"
        assert policy["status"] == "active"

    def test_observed_promotes_to_validated(self) -> None:
        policy = make_policy(tier="observed", confirms=6, contradicts=0)
        assert promote_policy(policy) is True
        assert policy["tier"] == "validated"

    def test_returns_false_when_nothing_changes(self) -> None:
        policy = make_policy(tier="observed", status="active", confirms=2)
        assert promote_policy(policy) is False

    def test_validated_policy_is_not_demoted_by_weak_evidence(self) -> None:
        # Evidence only qualifies for hypothesis, but a validated tier holds.
        policy = make_policy(tier="validated", status="active", confirms=0)
        promote_policy(policy)
        assert policy["tier"] == "validated"

    @pytest.mark.parametrize("start_tier", ["hypothesis", "observed", "validated"])
    def test_promote_never_lowers_tier_rank(self, start_tier: str) -> None:
        # No evidence => eligible tier is hypothesis; tier must not drop.
        policy = make_policy(tier=start_tier)
        promote_policy(policy)
        assert TIER_RANK[policy["tier"]] >= TIER_RANK[start_tier]


class TestPromotionBoundary:
    """Documented boundary: 5 confirms -> validated; 6th contradiction -> questioning."""

    def test_five_confirms_promote_then_sixth_contradiction_flips_questioning(
        self,
    ) -> None:
        policy = make_policy(tier="hypothesis")
        for index in range(5):
            assert add_evidence(policy, _confirmed(f"run-a::F{index}", ts=1000 + index))
        assert policy["confirms"] == 5.0
        assert policy["contradicts"] == 0

        assert promote_policy(policy) is True
        assert policy["tier"] == "validated"
        assert policy["status"] == "active"

        # The 6th run contradicts: contradict rate becomes 1/6 (~16.7%).
        assert add_evidence(policy, _contradicted("run-a::F5", ts=2000))
        assert promote_policy(policy) is True
        # Tier holds at validated; status surfaces the rising contradict rate.
        assert policy["tier"] == "validated"
        assert policy["status"] == "questioning"

    def test_questioning_recovers_to_active_when_rate_drops(self) -> None:
        # A validated/questioning policy whose rate falls back inside the gate
        # returns to active on the next promote pass.
        policy = make_policy(tier="validated", status="questioning")
        for index in range(19):
            add_evidence(policy, _confirmed(f"run-b::F{index}", ts=3000 + index))
        add_evidence(policy, _contradicted("run-b::C0", ts=4000))
        # 19 confirms + 1 contradict = 5% contradict rate.
        promote_policy(policy)
        assert policy["tier"] == "validated"
        assert policy["status"] == "active"


class TestRunPromote:
    """run_promote evaluates every policy and maintains the meta block."""

    def test_records_changed_policy_ids(self) -> None:
        data = {
            "schema_version": 1,
            "policies": [
                make_policy("pol-a", tier="hypothesis", confirms=1),
                make_policy("pol-b", tier="hypothesis", confirms=0),
            ],
            "meta": {
                "total_discovered": 0,
                "total_retired": 0,
                "total_merged": 0,
                "last_promotion_at": 0,
                "promotion_count": 0,
            },
        }
        changed = run_promote(data, now=5000)
        assert changed == ["pol-a"]
        assert data["meta"]["promotion_count"] == 1
        assert data["meta"]["last_promotion_at"] == 5000

    def test_is_noop_when_nothing_changes(self) -> None:
        data = {
            "schema_version": 1,
            "policies": [make_policy("pol-a", tier="hypothesis", confirms=0)],
            "meta": {
                "total_discovered": 0,
                "total_retired": 0,
                "total_merged": 0,
                "last_promotion_at": 0,
                "promotion_count": 0,
            },
        }
        changed = run_promote(data, now=5000)
        assert changed == []
        # A no-op promote leaves meta untouched so the operation is idempotent.
        assert data["meta"]["promotion_count"] == 0
        assert data["meta"]["last_promotion_at"] == 0


class TestAddEvidence:
    """add_evidence is the single mutation point for a policy's evidence."""

    def test_appends_and_bumps_version(self) -> None:
        policy = make_policy(version=1)
        assert add_evidence(policy, _confirmed("run-c::F0")) is True
        assert policy["version"] == 2
        assert policy["application_count"] == 1

    def test_idempotent_on_repeated_eval_id(self) -> None:
        policy = make_policy(version=1)
        assert add_evidence(policy, _confirmed("run-c::F0")) is True
        # Re-applying the same eval id is a no-op: no double count, no version bump.
        assert add_evidence(policy, _confirmed("run-c::F0")) is False
        assert policy["application_count"] == 1
        assert policy["version"] == 2

    def test_recomputes_counts_on_append(self) -> None:
        policy = make_policy()
        add_evidence(policy, make_evidence("confirmed", "run-d::F0"))
        add_evidence(policy, make_evidence("contradicted", "run-d::F1"))
        assert policy["confirms"] == 1.0
        assert policy["contradicts"] == 1.0
