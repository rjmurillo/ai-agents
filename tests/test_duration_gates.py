"""The per-leg wall time limit over a duration snapshot."""

from __future__ import annotations

from scripts.testing.duration_gates import (
    PARTITION_WALL_LIMIT_SECONDS,
    leg_breaches,
    legs_over_limit,
)
from tests.duration_gate_helpers import legs


def test_the_limit_is_eighty_percent_of_the_ten_minute_job_timeout() -> None:
    assert PARTITION_WALL_LIMIT_SECONDS == 0.8 * 10 * 60


class TestLegsOverLimit:
    def test_a_leg_above_the_limit_is_reported(self) -> None:
        assert legs_over_limit(legs(split_1=481.0, split_2=100.0), 480.0) == [
            ("pytest-results-split-1", 481.0)
        ]

    def test_a_leg_exactly_at_the_limit_passes(self) -> None:
        assert legs_over_limit(legs(split_1=480.0), 480.0) == []

    def test_dedicated_legs_are_checked_too(self) -> None:
        assert legs_over_limit(legs(safe_push=500.0), 480.0) == [
            ("pytest-results-safe-push", 500.0)
        ]

    def test_no_partitions_gives_no_violation(self) -> None:
        assert legs_over_limit({}, 480.0) == []

    def test_the_worst_leg_comes_first(self) -> None:
        over = legs_over_limit(legs(split_1=490.0, split_2=520.0), 480.0)
        assert [name for name, _ in over] == ["pytest-results-split-2", "pytest-results-split-1"]


class TestLegBreaches:
    def test_no_slow_leg_is_no_breach(self) -> None:
        assert leg_breaches("k", [], 480.0) == {}

    def test_every_slow_leg_lands_under_the_one_run_level_key(self) -> None:
        over = [("pytest-results-split-2", 520.04), ("pytest-results-split-1", 490.0)]
        assert leg_breaches("k", over, 480.0) == {
            "k": "pytest-results-split-2 took 520.0s, pytest-results-split-1 took 490.0s, "
            "above the 480s limit"
        }
