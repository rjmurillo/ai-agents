"""Workflow annotations for the duration gates."""

from __future__ import annotations

from scripts.testing.duration_gates import Imbalance, gate_commands

_IMBALANCE = Imbalance("pytest-results-split-1", 151.0, "pytest-results-split-2", 100.0)


class TestGateCommands:
    def test_an_over_limit_leg_is_an_error_annotation(self) -> None:
        (line,) = gate_commands([("pytest-results-split-1", 481.0)], None, 480.0)
        assert line.startswith("::error title=Test leg wall time::")
        assert "481.0s" in line and "480" in line

    def test_imbalance_is_a_warning_annotation_not_an_error(self) -> None:
        (line,) = gate_commands([], _IMBALANCE, 480.0)
        assert line.startswith("::warning title=Split imbalance::")
        assert "1.51x" in line

    def test_names_are_escaped(self) -> None:
        (line,) = gate_commands([("a%b\nc", 500.0)], None, 480.0)
        assert "a%25b%0Ac" in line and "\n" not in line

    def test_nothing_to_report_prints_nothing(self) -> None:
        assert gate_commands([], None, 480.0) == []
