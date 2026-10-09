"""Per-leg wall time limit and split imbalance gates over a duration snapshot."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.testing import duration_trend as trend
from scripts.testing.duration_gates import (
    PARTITION_WALL_LIMIT_SECONDS,
    SPLIT_IMBALANCE_RATIO,
    Imbalance,
    legs_over_limit,
    split_imbalance,
)
from scripts.testing.duration_render import gate_commands
from scripts.testing.duration_schema import PartitionEntry


def _legs(**seconds: float) -> dict[str, PartitionEntry]:
    return {
        f"pytest-results-{name.replace('_', '-')}": {"tests": 1, "wall_seconds": wall}
        for name, wall in seconds.items()
    }


def test_the_limit_is_eighty_percent_of_the_ten_minute_job_timeout() -> None:
    assert PARTITION_WALL_LIMIT_SECONDS == 0.8 * 10 * 60


class TestLegsOverLimit:
    def test_a_leg_above_the_limit_is_reported(self) -> None:
        assert legs_over_limit(_legs(split_1=481.0, split_2=100.0), 480.0) == [
            ("pytest-results-split-1", 481.0)
        ]

    def test_a_leg_exactly_at_the_limit_passes(self) -> None:
        assert legs_over_limit(_legs(split_1=480.0), 480.0) == []

    def test_dedicated_legs_are_checked_too(self) -> None:
        assert legs_over_limit(_legs(safe_push=500.0), 480.0) == [
            ("pytest-results-safe-push", 500.0)
        ]

    def test_no_partitions_gives_no_violation(self) -> None:
        assert legs_over_limit({}, 480.0) == []

    def test_the_worst_leg_comes_first(self) -> None:
        over = legs_over_limit(_legs(split_1=490.0, split_2=520.0), 480.0)
        assert [name for name, _ in over] == ["pytest-results-split-2", "pytest-results-split-1"]


class TestSplitImbalance:
    def test_slowest_over_one_and_a_half_times_fastest_is_flagged(self) -> None:
        found = split_imbalance(_legs(split_1=151.0, split_2=100.0, split_3=120.0), 1.5)
        assert found == Imbalance("pytest-results-split-1", 151.0, "pytest-results-split-2",
                                  100.0)

    def test_exactly_the_ratio_is_not_flagged(self) -> None:
        assert split_imbalance(_legs(split_1=150.0, split_2=100.0), 1.5) is None

    def test_a_balanced_split_is_not_flagged(self) -> None:
        assert split_imbalance(_legs(split_1=100.0, split_2=110.0), 1.5) is None

    def test_dedicated_legs_do_not_count_as_split_legs(self) -> None:
        assert split_imbalance(_legs(split_1=100.0, split_2=100.0, safe_push=1.0), 1.5) is None

    def test_a_single_split_leg_cannot_be_imbalanced(self) -> None:
        assert split_imbalance(_legs(split_1=100.0), 1.5) is None

    def test_a_zero_second_fastest_leg_is_skipped_not_divided(self) -> None:
        assert split_imbalance(_legs(split_1=100.0, split_2=0.0), 1.5) is None

    def test_the_default_ratio_is_one_and_a_half(self) -> None:
        assert SPLIT_IMBALANCE_RATIO == 1.5


class TestGateCommands:
    def test_an_over_limit_leg_is_an_error_annotation(self) -> None:
        (line,) = gate_commands([("pytest-results-split-1", 481.0)], None, 480.0)
        assert line.startswith("::error title=Test leg wall time::")
        assert "481.0s" in line and "480" in line

    def test_imbalance_is_a_warning_annotation_not_an_error(self) -> None:
        imbalance = Imbalance("pytest-results-split-1", 151.0, "pytest-results-split-2", 100.0)
        (line,) = gate_commands([], imbalance, 480.0)
        assert line.startswith("::warning title=Split imbalance::")
        assert "1.51x" in line

    def test_names_are_escaped(self) -> None:
        (line,) = gate_commands([("a%b\nc", 500.0)], None, 480.0)
        assert "a%25b%0Ac" in line and "\n" not in line

    def test_nothing_to_report_prints_nothing(self) -> None:
        assert gate_commands([], None, 480.0) == []


def _write_legs(tmp_path: Path, **walls: float) -> list[str]:
    from tests.duration_test_helpers import write_junit

    return [
        str(write_junit(tmp_path, f"pytest-results-{name.replace('_', '-')}",
                        {f"tests.test_{name}": [1.0]}, wall))
        for name, wall in walls.items()
    ]


class TestTrendCliWiring:
    def test_a_slow_leg_exits_one_with_an_error_annotation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        inputs = _write_legs(tmp_path, split_1=481.0, split_2=470.0)
        assert trend.main(inputs) == 1
        assert "::error title=Test leg wall time::" in capsys.readouterr().out

    def test_a_leg_at_the_limit_exits_zero(self, tmp_path: Path) -> None:
        assert trend.main(_write_legs(tmp_path, split_1=480.0, split_2=470.0)) == 0

    def test_the_limit_is_configurable(self, tmp_path: Path) -> None:
        inputs = _write_legs(tmp_path, split_1=60.0, split_2=59.0)
        assert trend.main([*inputs, "--leg-limit", "50"]) == 1

    def test_imbalance_warns_and_still_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        inputs = _write_legs(tmp_path, split_1=200.0, split_2=100.0)
        assert trend.main(inputs) == 0
        assert "::warning title=Split imbalance::" in capsys.readouterr().out

    def test_balanced_legs_print_no_gate_annotation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        trend.main(_write_legs(tmp_path, split_1=100.0, split_2=110.0))
        out = capsys.readouterr().out
        assert "Split imbalance" not in out and "Test leg wall time" not in out

    def test_a_custom_imbalance_ratio_applies(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        inputs = _write_legs(tmp_path, split_1=120.0, split_2=100.0)
        trend.main([*inputs, "--imbalance-ratio", "1.1"])
        assert "::warning title=Split imbalance::" in capsys.readouterr().out

    def test_the_history_is_still_written_when_a_leg_is_too_slow(self, tmp_path: Path) -> None:
        history = tmp_path / "history.json"
        inputs = _write_legs(tmp_path, split_1=500.0, split_2=490.0)
        assert trend.main([*inputs, "--write-history", str(history)]) == 1
        assert history.is_file()
