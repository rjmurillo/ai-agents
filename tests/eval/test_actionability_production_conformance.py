"""The eval arms use the thresholds production uses (review finding 9).

Plan M1-T13 and M1-T14. The thresholds are located in `scripts/update_reviewer_signal_stats.py`
by walking its AST, not by line number, so an edit elsewhere in that file cannot silently
move the target. If the structure changes, the lookup fails loudly instead of passing.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.eval._actionability_arms_test_support import aa, make_prediction, make_row

_PRODUCTION = Path(__file__).resolve().parents[2] / "scripts" / "update_reviewer_signal_stats.py"
_OPERATORS: dict[type[ast.cmpop], Callable[[float, float], bool]] = {
    ast.GtE: operator.ge,
    ast.Gt: operator.gt,
    ast.LtE: operator.le,
    ast.Lt: operator.lt,
}


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(_PRODUCTION.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {_PRODUCTION.name}")


def _single_compare(node: ast.AST) -> tuple[Callable[[float, float], bool], float]:
    assert isinstance(node, ast.Compare), ast.dump(node)
    assert len(node.ops) == 1 and len(node.comparators) == 1
    right = node.comparators[0]
    assert isinstance(right, ast.Constant) and isinstance(right.value, float)
    return _OPERATORS[type(node.ops[0])], right.value


def _production_actionable_rule() -> tuple[Callable[[float, float], bool], float]:
    """The comparison in `is_actionable=score >= 0.5` inside get_actionability_score."""
    for node in ast.walk(_function("get_actionability_score")):
        if isinstance(node, ast.keyword) and node.arg == "is_actionable":
            if isinstance(node.value, ast.Compare):
                return _single_compare(node.value)
    raise AssertionError("no `is_actionable=score <op> <const>` found in get_actionability_score")


def _production_apply_rule() -> tuple[Callable[[float, float], bool], float]:
    """The comparison `llm_result.confidence <op> <const>` inside get_actionability_score."""
    for node in ast.walk(_function("get_actionability_score")):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Attribute):
            if node.left.attr == "confidence":
                return _single_compare(node)
    raise AssertionError("no `<x>.confidence <op> <const>` found in get_actionability_score")


class TestHeuristicThreshold:
    def test_the_arm_a_constant_equals_production(self) -> None:
        """HEURISTIC_THRESHOLD is the constant in production's `score >= 0.5`."""
        _, threshold = _production_actionable_rule()

        assert aa.HEURISTIC_THRESHOLD == threshold == 0.5

    def test_production_uses_greater_or_equal_so_arm_a_does_the_same(self) -> None:
        """Arm A is production as shipped: the tie at the threshold is actionable."""
        compare, threshold = _production_actionable_rule()

        assert compare is operator.ge
        for score in (threshold - 0.01, threshold, threshold + 0.01):
            assert aa.arm_a(make_row("r", score=score)) is compare(score, threshold)

    def test_arm_b_is_the_opposite_tie_break(self) -> None:
        """Arm B differs from production only at the threshold itself."""
        compare, threshold = _production_actionable_rule()

        assert aa.arm_b(make_row("r", score=threshold)) is (not compare(threshold, threshold))


class TestApplyConfidence:
    def test_the_arm_c_constant_equals_production(self) -> None:
        """APPLY_CONFIDENCE is the constant in production's confidence gate."""
        _, threshold = _production_apply_rule()

        assert aa.APPLY_CONFIDENCE == threshold == 0.7

    @pytest.mark.parametrize("confidence", [0.69, 0.7, 0.71])
    def test_arm_c_applies_the_verdict_exactly_when_production_would(
        self, confidence: float
    ) -> None:
        """Same operator and constant: >= 0.7 applies the model, below it keeps the heuristic."""
        compare, threshold = _production_apply_rule()
        row = make_row("r", score=0.5)
        prediction = aa.Prediction.from_dict(
            make_prediction("r", is_actionable=False, confidence=confidence)
        )

        applied = aa.arm_c(row, prediction) is False

        assert applied is compare(confidence, threshold)


class TestLookupFailsLoudly:
    def test_a_missing_function_is_an_assertion_not_a_pass(self) -> None:
        """If production renames the function, the lookup raises rather than skipping."""
        with pytest.raises(AssertionError, match="not found"):
            _function("no_such_function_in_production")
