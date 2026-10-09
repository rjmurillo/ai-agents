"""Reading one per-leg durations file."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.testing.duration_split_merge import load_durations
from tests.duration_split_merge_helpers import write_json


class TestLoadDurations:
    def test_reads_node_ids_and_seconds(self, tmp_path: Path) -> None:
        loaded = load_durations(write_json(tmp_path / "d", {"a::t": 1, "b::t": 2.5}))
        assert loaded == {"a::t": 1.0, "b::t": 2.5}

    @pytest.mark.parametrize(
        "payload",
        [[1, 2], {"a::t": "soon"}, {"a::t": True}, {"a::t": -1.0}, {"a::t": None}],
    )
    def test_rejects_a_malformed_map(self, tmp_path: Path, payload: object) -> None:
        with pytest.raises(ValueError):
            load_durations(write_json(tmp_path / "d", payload))

    @pytest.mark.parametrize("text", ['{"a::t": Infinity}', "{"])
    def test_rejects_non_finite_values_and_bad_json(self, tmp_path: Path, text: str) -> None:
        path = tmp_path / "d"
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            load_durations(path)
