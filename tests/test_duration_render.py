"""Tests for the duration report markdown and workflow annotations."""

from __future__ import annotations

from pathlib import Path

from scripts.testing import duration_trend as trend
from scripts.testing.duration_compare import Comparison, Regression
from scripts.testing.duration_render import ratio_text, warning_commands
from tests.duration_test_helpers import write_history, write_junit


def test_ratio_text_formats_the_ratio_and_a_zero_baseline_as_new() -> None:
    assert ratio_text(Regression("m", 30.0, 10.0, 2)) == "3.00x"
    assert ratio_text(Regression("m", 15.0, 0.0, 1)) == "new"


def test_warning_data_escapes_newlines_and_percent() -> None:
    comparison = Comparison(modules=[Regression("a%b\nc", 30.0, 10.0, 2)])

    (line,) = warning_commands(comparison)

    assert "a%25b%0Ac took 30.0s" in line
    assert "\n" not in line


def test_the_trend_table_lists_history_then_this_run(tmp_path: Path) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0, 1.0]}, 2.0)
    summary = tmp_path / "summary.md"

    trend.main([str(report), "--history", str(write_history(tmp_path, [3.0] * 12)),
                "--summary", str(summary), "--sha", "current99"])

    rows = [r for r in summary.read_text(encoding="utf-8").splitlines()
            if r.startswith("| `sha") or r.startswith("| `current")]
    assert len(rows) == 10
    assert rows[0].startswith("| `sha3`") and rows[-1].startswith("| `current99`")
