"""Merging per-leg pytest-split durations: the pure union."""

from __future__ import annotations

from scripts.testing.duration_split_merge import merge_durations


class TestMergeDurations:
    def test_unions_disjoint_maps(self) -> None:
        assert merge_durations([{"a::t": 1.0}, {"b::t": 2.0}]) == {"a::t": 1.0, "b::t": 2.0}

    def test_the_later_value_wins_on_a_shared_key(self) -> None:
        assert merge_durations([{"a::t": 1.0}, {"a::t": 9.0}]) == {"a::t": 9.0}

    def test_no_maps_gives_an_empty_map(self) -> None:
        assert merge_durations([]) == {}

    def test_does_not_mutate_its_inputs(self) -> None:
        first = {"a::t": 1.0}
        merge_durations([first, {"b::t": 2.0}])
        assert first == {"a::t": 1.0}
