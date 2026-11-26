"""Scenario file parsing in ``skill_rewrite_scenarios.py``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.validation.skill_rewrite_helpers import RUNNER

import skill_rewrite_scenarios as scenarios  # isort: skip

ROWS = [{"id": f"S{i}", "desc": "d", "input": "i", "expected_verdict": "GO"} for i in range(1, 3)]


class TestRunnerShapes:
    """The check reads the corpus shapes ``load_scenarios`` in the runner loads."""

    @pytest.mark.parametrize(
        "corpus",
        [
            {"scenarios": ROWS},
            ROWS,
            {"other": ROWS},
            {"scenarios": "text"},
            {"scenarios": {"id": "S1"}},
            "text",
            5,
            None,
        ],
    )
    def test_accepts_what_the_runner_accepts(self, tmp_path: Path, corpus: Any) -> None:
        path = tmp_path / "s.json"
        path.write_text(json.dumps(corpus), encoding="utf-8")
        try:
            RUNNER.load_scenarios(str(path))
            runner_accepts = True
        except RuntimeError:
            runner_accepts = False
        assert (scenarios.scenario_rows(path.read_bytes()) is not None) == runner_accepts

    @pytest.mark.parametrize("corpus", [[], [{"id": "S1"}]])
    def test_documented_divergence_from_the_runner(self, tmp_path: Path, corpus: Any) -> None:
        """The runner rejects these; the check reads them and leaves floors to the results."""
        path = tmp_path / "s.json"
        path.write_text(json.dumps(corpus), encoding="utf-8")
        with pytest.raises(RuntimeError):
            RUNNER.load_scenarios(str(path))
        assert scenarios.scenario_rows(path.read_bytes()) == corpus

    def test_top_level_array_yields_its_rows(self) -> None:
        assert scenarios.scenario_rows(json.dumps(ROWS).encode()) == ROWS

    def test_object_form_yields_its_rows(self) -> None:
        assert scenarios.scenario_rows(json.dumps({"scenarios": ROWS}).encode()) == ROWS

    @pytest.mark.parametrize("data", [b"{", b"\xff\xfe", b"[1, 2]", b'[{"desc": "no id"}]'])
    def test_malformed_corpus_is_none(self, data: bytes) -> None:
        assert scenarios.scenario_rows(data) is None
