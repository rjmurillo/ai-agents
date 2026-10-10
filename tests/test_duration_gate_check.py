"""The leg wall time gate CLI: a slow leg fails, an uneven split only warns."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.testing.duration_gate_check import main
from tests.duration_gate_helpers import write_legs


class TestGateCheck:
    def test_a_slow_leg_exits_one_with_an_error_annotation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(write_legs(tmp_path, split_1=481.0, split_2=470.0)) == 1
        assert "::error title=Test leg wall time::" in capsys.readouterr().out

    def test_a_leg_at_the_limit_exits_zero(self, tmp_path: Path) -> None:
        assert main(write_legs(tmp_path, split_1=480.0, split_2=470.0)) == 0

    def test_the_limit_is_configurable(self, tmp_path: Path) -> None:
        assert main([*write_legs(tmp_path, split_1=60.0, split_2=59.0), "--leg-limit", "50"]) == 1

    def test_imbalance_warns_and_still_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(write_legs(tmp_path, split_1=200.0, split_2=100.0)) == 0
        assert "::warning title=Split imbalance::" in capsys.readouterr().out

    def test_balanced_legs_print_no_annotation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(write_legs(tmp_path, split_1=100.0, split_2=110.0))
        assert "::" not in capsys.readouterr().out
