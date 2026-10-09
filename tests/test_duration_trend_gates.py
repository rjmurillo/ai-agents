"""The duration trend CLI applies the wall time gates."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.testing import duration_trend as trend
from tests.duration_gate_helpers import write_legs


class TestTrendCliGates:
    def test_a_slow_leg_exits_one_with_an_error_annotation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert trend.main(write_legs(tmp_path, split_1=481.0, split_2=470.0)) == 1
        assert "::error title=Test leg wall time::" in capsys.readouterr().out

    def test_a_leg_at_the_limit_exits_zero(self, tmp_path: Path) -> None:
        assert trend.main(write_legs(tmp_path, split_1=480.0, split_2=470.0)) == 0

    def test_the_limit_is_configurable(self, tmp_path: Path) -> None:
        inputs = write_legs(tmp_path, split_1=60.0, split_2=59.0)
        assert trend.main([*inputs, "--leg-limit", "50"]) == 1

    def test_imbalance_warns_and_still_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert trend.main(write_legs(tmp_path, split_1=200.0, split_2=100.0)) == 0
        assert "::warning title=Split imbalance::" in capsys.readouterr().out

    def test_balanced_legs_print_no_gate_annotation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        trend.main(write_legs(tmp_path, split_1=100.0, split_2=110.0))
        out = capsys.readouterr().out
        assert "Split imbalance" not in out and "Test leg wall time" not in out

    def test_a_custom_imbalance_ratio_applies(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        inputs = write_legs(tmp_path, split_1=120.0, split_2=100.0)
        trend.main([*inputs, "--imbalance-ratio", "1.1"])
        assert "::warning title=Split imbalance::" in capsys.readouterr().out

    def test_the_history_is_still_written_when_a_leg_is_too_slow(self, tmp_path: Path) -> None:
        history = tmp_path / "history.json"
        inputs = write_legs(tmp_path, split_1=500.0, split_2=490.0)
        assert trend.main([*inputs, "--write-history", str(history)]) == 1
        assert history.is_file()
