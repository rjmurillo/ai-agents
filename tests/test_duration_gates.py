"""The per-leg wall time limit over a duration snapshot."""

from __future__ import annotations

from scripts.testing.duration_gates import PARTITION_WALL_LIMIT_SECONDS, legs_over_limit
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
