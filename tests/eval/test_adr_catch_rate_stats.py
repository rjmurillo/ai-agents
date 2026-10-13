"""Tests for scripts/eval/_adr_catch_rate_stats.py (issue #5248)."""

from __future__ import annotations

import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import _adr_catch_rate_stats as stats  # noqa: E402


def test_wilson_interval_bounds():
    assert stats.wilson_interval(0, 0) == (0.0, 1.0)
    low, high = stats.wilson_interval(5, 10)
    assert 0.2 < low < 0.5 < high < 0.8
    low0, high0 = stats.wilson_interval(0, 10)
    assert low0 == 0.0 and 0.2 < high0 < 0.35
    low1, high1 = stats.wilson_interval(10, 10)
    assert high1 == 1.0 and 0.65 < low1 < 0.8


def _row(entry, arm, role, flagged, blocked, error=None):
    return {
        "entry": entry,
        "arm": arm,
        "role": role,
        "trial": 0,
        "flagged": flagged,
        "blocked": blocked,
        "error": error,
    }


def test_aggregate_counts_hits_and_keeps_errors_out_of_n():
    rows = [
        _row("A", "unassisted", "critic", True, True),
        _row("B", "unassisted", "critic", True, False),
        _row("C", "unassisted", "critic", False, False),
        _row("D", "unassisted", "critic", False, False, error="boom"),
    ]
    cell = stats.aggregate(rows)["unassisted"]["critic"]
    assert cell["flagged"]["hits"] == 2 and cell["flagged"]["n"] == 3
    assert cell["blocked"]["hits"] == 1
    assert cell["errors"] == 1


def test_aggregate_rate_is_none_without_trials():
    cell = stats.aggregate([_row("A", "control", "critic", False, False, error="x")])
    assert cell["control"]["critic"]["flagged"]["rate"] is None


def test_panel_union_counts_an_entry_once_if_any_role_caught_it():
    rows = [
        _row("A", "unassisted", "critic", True, False),
        _row("A", "unassisted", "security", True, True),
        _row("B", "unassisted", "critic", False, False),
        _row("B", "assisted", "critic", True, True),
        _row("C", "unassisted", "critic", False, False, error="x"),
    ]
    union = stats.panel_union(rows, "unassisted")
    assert union["flagged"]["hits"] == 1 and union["flagged"]["n"] == 2
    assert union["blocked"]["hits"] == 1


def test_render_report_lists_roles_arms_and_union():
    rows = [
        _row("A", "unassisted", "critic", True, False),
        _row("A", "control", "critic", False, False),
        _row("A", "unassisted", "analyst", False, False),
    ]
    text = stats.render_report(
        stats.aggregate(rows),
        {"unassisted": stats.panel_union(rows, "unassisted")},
        {"model": "m", "trials": 1, "entries": 1},
    )
    assert "## Arm: unassisted" in text and "## Arm: control" in text
    assert "| critic | 1/1" in text and "| any role |" in text
    assert "assisted" not in text.replace("unassisted", "")
    assert "n/a" not in text


def test_render_report_shows_not_available_for_an_empty_cell():
    rows = [_row("A", "control", "critic", False, False, error="x")]
    text = stats.render_report(stats.aggregate(rows), {}, {})
    assert "n/a" in text
