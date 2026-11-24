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
    "actionability_predict.py",
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
    "fetched",
    "no_hunk",
    "auth_error",
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


_PROVENANCE = {"provider", "model", "prompt_sha256"}
_ALL_MODULES = [
    "actionability_corpus.py",
    "actionability_score.py",
    "actionability_arms.py",
    "actionability_predict.py",
    "actionability_validate.py",
    "actionability_scan.py",
    "actionability_verdict.py",
]


def _sequence_literals(path: Path) -> list[set[str]]:
    """The string constants of every tuple, list, and set literal in a module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple | ast.List | ast.Set):
            found.append(
                {
                    e.value
                    for e in node.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                }
            )
    return found


class TestProvenanceFieldsSingleSource:
    """Review finding 8: PROVENANCE_FIELDS is defined once, in the labels module."""

    def test_the_owner_defines_the_tuple(self) -> None:
        """The tuple lives in actionability_labels.py."""
        assert set(_LABELS.PROVENANCE_FIELDS) == _PROVENANCE
        assert isinstance(_LABELS.PROVENANCE_FIELDS, tuple)

    @pytest.mark.parametrize("module", _ALL_MODULES)
    def test_no_other_module_spells_the_three_names_as_one_sequence(self, module: str) -> None:
        """A second tuple or list of the three names is a copy that can drift."""
        offenders = [s for s in _sequence_literals(_EVAL_DIR / module) if _PROVENANCE <= s]

        assert offenders == []

    def test_consumers_use_the_owner_object(self) -> None:
        """Predict and score read the same tuple object."""
        score = importlib.import_module("scripts.eval.actionability_score")
        predict = importlib.import_module("scripts.eval.actionability_predict")

        assert score.PROVENANCE_FIELDS is _LABELS.PROVENANCE_FIELDS
        assert predict.PROVENANCE_FIELDS is _LABELS.PROVENANCE_FIELDS
