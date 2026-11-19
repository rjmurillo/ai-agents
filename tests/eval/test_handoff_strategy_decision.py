"""Frozen decision rule for the strategy comparison (issue #7350)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _handoff_strategy as hs  # noqa: E402


def row(task: str, arm: str, **kw: Any) -> dict[str, Any]:
    base = {
        "task_id": task,
        "arm": arm,
        "valid": True,
        "accepted": False,
        "regression": False,
        "scope_violations": 0,
        "wall_seconds": 10.0,
    }
    return {**base, **kw}


def grid(passes: dict[str, int], task: str, **kw: Any) -> list[dict[str, Any]]:
    return [row(task, arm, accepted=i < passes[arm], **kw) for arm in hs.ARMS for i in range(3)]


class TestDecision:
    def test_one_stalled_task_is_inconclusive_whatever_the_gain(self) -> None:
        entries = grid({hs.ARM_CONTINUE: 0, hs.ARM_HANDOFF: 3}, "s") + grid(
            {hs.ARM_CONTINUE: 3, hs.ARM_HANDOFF: 3}, "n"
        )
        out = hs.decide(entries, {"s"}, {"n"}, 12)
        assert out["outcome"] == "INCONCLUSIVE"
        assert out["routing"] == "retain incumbent"

    def test_two_stalled_tasks_with_a_gain_support_a_narrow_change(self) -> None:
        entries = (
            grid({hs.ARM_CONTINUE: 0, hs.ARM_HANDOFF: 2}, "s1")
            + grid({hs.ARM_CONTINUE: 1, hs.ARM_HANDOFF: 3}, "s2")
            + grid({hs.ARM_CONTINUE: 3, hs.ARM_HANDOFF: 3}, "n")
        )
        out = hs.decide(entries, {"s1", "s2"}, {"n"}, 18)
        assert out["outcome"] == "SUPPORTED_NARROW"

    def test_a_gain_of_one_is_not_enough(self) -> None:
        entries = grid({hs.ARM_CONTINUE: 1, hs.ARM_HANDOFF: 2}, "s1") + grid(
            {hs.ARM_CONTINUE: 1, hs.ARM_HANDOFF: 1}, "s2"
        )
        assert hs.decide(entries, {"s1", "s2"}, set(), 12)["outcome"] == "INCONCLUSIVE"

    def test_a_slow_treatment_does_not_earn_support(self) -> None:
        entries = grid({hs.ARM_CONTINUE: 0, hs.ARM_HANDOFF: 3}, "s1") + grid(
            {hs.ARM_CONTINUE: 0, hs.ARM_HANDOFF: 3}, "s2"
        )
        for e in entries:
            if e["arm"] == hs.ARM_HANDOFF:
                e["wall_seconds"] = 100.0
        assert hs.decide(entries, {"s1", "s2"}, set(), 12)["outcome"] == "INCONCLUSIVE"

    def test_a_worse_negative_control_rejects(self) -> None:
        entries = grid({hs.ARM_CONTINUE: 0, hs.ARM_HANDOFF: 3}, "s") + grid(
            {hs.ARM_CONTINUE: 3, hs.ARM_HANDOFF: 2}, "n"
        )
        assert hs.decide(entries, {"s"}, {"n"}, 12)["outcome"] == "REJECT"

    def test_a_scope_violation_in_the_negative_control_rejects(self) -> None:
        entries = grid({hs.ARM_CONTINUE: 3, hs.ARM_HANDOFF: 3}, "n")
        entries[3]["scope_violations"] = 1
        assert hs.decide(entries, set(), {"n"}, 6)["outcome"] == "REJECT"

    def test_a_missed_regression_on_a_stalled_task_rejects(self) -> None:
        entries = grid({hs.ARM_CONTINUE: 0, hs.ARM_HANDOFF: 3}, "s")
        entries[3]["regression"] = True
        assert hs.decide(entries, {"s"}, set(), 6)["outcome"] == "REJECT"

    def test_an_invalid_or_missing_cell_is_inconclusive(self) -> None:
        entries = grid({hs.ARM_CONTINUE: 3, hs.ARM_HANDOFF: 3}, "s")
        assert hs.decide(entries[:-1], {"s"}, set(), 6)["outcome"] == "INCONCLUSIVE"
        entries[0]["valid"] = False
        assert hs.decide(entries, {"s"}, set(), 6)["outcome"] == "INCONCLUSIVE"

    def test_wilson_interval_brackets_the_proportion(self) -> None:
        low, high = hs.wilson(3, 3)
        assert 0.4 < low < 1.0 and high == 1.0
        assert hs.wilson(0, 0) == (0.0, 1.0)
