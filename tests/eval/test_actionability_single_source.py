"""Structural guards: label, split, and status literals live in one module.

Plan M1-T15 follow-up, hygiene 6a. The AST walk skips docstrings and finds every
string constant, so a module that redefines a literal fails here.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
_LABELS = importlib.import_module("scripts.eval.actionability_labels")

_OWNER = "actionability_labels.py"
_CONSUMERS = [
    "actionability_corpus.py",
    "actionability_score.py",
    "actionability_arms.py",
]
_LITERALS = {
    "actionable",
    "not_actionable",
    "unsure",
    "dev",
    "heldout",
    "outside",
    "ok",
    "parse_error",
    "call_error",
}


def _string_constants(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            value = body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                docstrings.add(id(value))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


class TestSingleSource:
    def test_the_owner_module_defines_every_literal(self) -> None:
        """Hygiene 6a: actionability_labels.py holds the literals."""
        assert _LITERALS <= _string_constants(_EVAL_DIR / _OWNER)

    @pytest.mark.parametrize("module", _CONSUMERS)
    def test_consumers_do_not_redefine_the_literals(self, module: str) -> None:
        """Hygiene 6a: consumers import the constants, they do not repeat the strings."""
        repeated = _string_constants(_EVAL_DIR / module) & _LITERALS

        assert repeated == set()

    def test_exported_constants_are_the_owner_objects(self) -> None:
        """Hygiene 6a: the names consumers use resolve to the owner module."""
        corpus = importlib.import_module("scripts.eval.actionability_corpus")
        score = importlib.import_module("scripts.eval.actionability_score")

        assert corpus.VALID_LABELS is _LABELS.VALID_LABELS
        assert score.LABEL_TRUTH is _LABELS.LABEL_TRUTH
        assert score.STATUSES is _LABELS.STATUSES
