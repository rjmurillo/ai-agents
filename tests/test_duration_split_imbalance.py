"""The split imbalance check: slowest split leg against the fastest."""

from __future__ import annotations

from scripts.testing.duration_gates import SPLIT_IMBALANCE_RATIO, Imbalance, split_imbalance
from tests.duration_gate_helpers import legs


class TestSplitImbalance:
    def test_slowest_over_one_and_a_half_times_fastest_is_flagged(self) -> None:
        found = split_imbalance(legs(split_1=151.0, split_2=100.0, split_3=120.0), 1.5)
        assert found == Imbalance("pytest-results-split-1", 151.0, "pytest-results-split-2", 100.0)

    def test_exactly_the_ratio_is_not_flagged(self) -> None:
        assert split_imbalance(legs(split_1=150.0, split_2=100.0), 1.5) is None

    def test_a_balanced_split_is_not_flagged(self) -> None:
        assert split_imbalance(legs(split_1=100.0, split_2=110.0), 1.5) is None

    def test_dedicated_legs_do_not_count_as_split_legs(self) -> None:
        assert split_imbalance(legs(split_1=100.0, split_2=100.0, safe_push=1.0), 1.5) is None

    def test_a_single_split_leg_cannot_be_imbalanced(self) -> None:
        assert split_imbalance(legs(split_1=100.0), 1.5) is None

    def test_a_zero_second_fastest_leg_is_skipped_not_divided(self) -> None:
        assert split_imbalance(legs(split_1=100.0, split_2=0.0), 1.5) is None

    def test_the_default_ratio_is_one_and_a_half(self) -> None:
        assert SPLIT_IMBALANCE_RATIO == 1.5
