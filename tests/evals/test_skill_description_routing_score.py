"""Gate margin tests for evals/skill-description-routing/score.py.

G1 and G2 are inclusive at 0.03. A change that lands exactly on the margin
must pass, and one result past it must fail. No live calls: rows are built here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCORE_PATH = (
    Path(__file__).resolve().parents[2] / "evals" / "skill-description-routing" / "score.py"
)


def _load_score() -> ModuleType:
    spec = importlib.util.spec_from_file_location("skill_description_routing_score", SCORE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


score = _load_score()

Pair = tuple[dict[str, Any], dict[str, Any]]


def _pairs(n: int, before: dict[str, int], after: dict[str, int]) -> list[Pair]:
    """Build n pairs; each arm maps an outcome to how many rows carry it, rest are correct."""

    def arm(counts: dict[str, int]) -> list[str]:
        rows = [outcome for outcome, count in counts.items() for _ in range(count)]
        return rows + ["correct"] * (n - len(rows))

    return [({"outcome": b}, {"outcome": a}) for b, a in zip(arm(before), arm(after), strict=True)]


@pytest.mark.parametrize(
    ("n", "lost", "passes"),
    [(100, 3, True), (100, 4, False), (200, 6, True), (200, 7, False), (340, 10, True)],
)
def test_g1_is_inclusive_at_the_three_point_margin(n: int, lost: int, passes: bool) -> None:
    result = score.rates(_pairs(n, {}, {"none": lost}))

    assert result["G1"] is passes
    assert result["d_correct"] == round(-lost / n, 4)


@pytest.mark.parametrize(
    ("n", "more_wrong", "passes"),
    [(100, 3, True), (100, 4, False), (200, 6, True), (200, 7, False)],
)
def test_g2_is_inclusive_at_the_three_point_margin(n: int, more_wrong: int, passes: bool) -> None:
    result = score.rates(_pairs(n, {}, {"wrong": more_wrong}))

    assert result["G2"] is passes
    assert result["d_wrong"] == round(more_wrong / n, 4)


def test_gains_pass_both_rate_gates() -> None:
    result = score.rates(_pairs(100, {"none": 5, "wrong": 2}, {}))

    assert result["G1"] is True
    assert result["G2"] is True
    assert result["after_wins"] == 7
    assert result["before_wins"] == 0


def test_no_pairs_reports_only_the_count() -> None:
    assert score.rates([]) == {"n": 0}
