"""The fallback band policy lives in one library module (review finding 8).

Plan M1-T2. `actionability_band.py` owns BAND_MIN, BAND_MAX, is_in_band, thread_position,
and UNKNOWN_POSITION. The band CLI and the corpus builder import them, so the corpus no
longer depends on the measurement script. Conformance with production is checked against
`LLMFallbackConfig`, the class whose defaults the band mirrors.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

from scripts.llm_classification.config import LLMFallbackConfig
from scripts.update_reviewer_signal_stats import CommentData

band = importlib.import_module("scripts.eval.actionability_band")
corpus = importlib.import_module("scripts.eval.actionability_corpus")

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"


def _load_band_cli() -> object:
    spec = importlib.util.spec_from_file_location(
        "band_cli_probe", _EVAL_DIR / "measure_actionability_band.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


band_cli = _load_band_cli()


def _comment(body: str = "b", created: str = "t") -> CommentData:
    return CommentData(
        pr_number=1,
        body=body,
        created_at=created,
        path="a.py",
        is_resolved=False,
        is_outdated=False,
        thread_comments=[
            {"body": "first", "createdAt": "t0"},
            {"body": "b", "createdAt": "t"},
            {"body": "third", "createdAt": "t2"},
        ],
    )


class TestBandPolicy:
    def test_band_edges_are_inclusive(self) -> None:
        """Plan M1-T2: 0.4 and 0.6 are in the band."""
        assert band.is_in_band(0.4) is True
        assert band.is_in_band(0.6) is True

    @pytest.mark.parametrize("score", [0.0, 0.39, 0.61, 1.0])
    def test_scores_outside_are_not_in_the_band(self, score: float) -> None:
        """Plan M1-T2: only 0.4 to 0.6 counts."""
        assert band.is_in_band(score) is False

    def test_constants_are_the_documented_band(self) -> None:
        """Plan M1-T2: 0.4 to 0.6."""
        assert (band.BAND_MIN, band.BAND_MAX) == (0.4, 0.6)

    def test_thread_position_finds_the_matching_node(self) -> None:
        """Plan M1-T2: position is the node's index in its thread."""
        assert band.thread_position(_comment("b", "t")) == 1
        assert band.thread_position(_comment("first", "t0")) == 0

    def test_thread_position_is_unknown_for_a_missing_node(self) -> None:
        """Plan M1-T2: no match gives the sentinel."""
        assert band.thread_position(_comment("nope", "t")) == band.UNKNOWN_POSITION == -1


class TestMirrorsProduction:
    def test_band_bounds_equal_the_production_defaults(self) -> None:
        """Conformance: the eval band is LLMFallbackConfig's default range."""
        config = LLMFallbackConfig()

        assert band.BAND_MIN == config.low_confidence_min
        assert band.BAND_MAX == config.low_confidence_max

    @pytest.mark.parametrize("score", [0.0, 0.3, 0.39, 0.4, 0.5, 0.6, 0.61, 0.7, 1.0])
    def test_is_in_band_agrees_with_the_production_predicate(self, score: float) -> None:
        """Conformance: same answer as `LLMFallbackConfig.is_low_confidence`."""
        assert band.is_in_band(score) == LLMFallbackConfig().is_low_confidence(score)


class TestSingleSource:
    def test_cli_and_corpus_use_the_library_objects(self) -> None:
        """Identity: no second copy of the functions or the sentinel."""
        assert band_cli.is_in_band is band.is_in_band  # type: ignore[attr-defined]
        assert band_cli.thread_position is band.thread_position  # type: ignore[attr-defined]
        assert corpus.is_in_band is band.is_in_band
        assert corpus.thread_position is band.thread_position
        assert corpus.UNKNOWN_POSITION == band.UNKNOWN_POSITION
        assert band_cli.BAND_MIN == band.BAND_MIN  # type: ignore[attr-defined]

    @pytest.mark.parametrize("module", ["measure_actionability_band.py", "actionability_corpus.py"])
    def test_neither_module_defines_the_policy_itself(self, module: str) -> None:
        """AST: the policy functions and constants are defined in the library only."""
        tree = ast.parse((_EVAL_DIR / module).read_text(encoding="utf-8"))
        defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assigned = {
            t.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            for t in n.targets
            if isinstance(t, ast.Name)
        }

        assert not {"is_in_band", "thread_position"} & defined
        assert not {"BAND_MIN", "BAND_MAX", "UNKNOWN_POSITION"} & assigned

    def test_the_corpus_does_not_import_the_measurement_script(self) -> None:
        """The corpus builder depends on the library, not on a CLI."""
        source = (_EVAL_DIR / "actionability_corpus.py").read_text(encoding="utf-8")

        assert "measure_actionability_band" not in source
        assert "actionability_band" in source
