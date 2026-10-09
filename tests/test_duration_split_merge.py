"""Merging the per-leg pytest-split durations into one map for the Actions cache."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.testing.duration_split_merge import load_durations, main, merge_durations


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestMergeDurations:
    def test_unions_disjoint_maps(self) -> None:
        assert merge_durations([{"a::t": 1.0}, {"b::t": 2.0}]) == {"a::t": 1.0, "b::t": 2.0}

    def test_the_later_value_wins_on_a_shared_key(self) -> None:
        assert merge_durations([{"a::t": 1.0}, {"a::t": 9.0}]) == {"a::t": 9.0}

    def test_no_maps_gives_an_empty_map(self) -> None:
        assert merge_durations([]) == {}

    def test_does_not_mutate_its_inputs(self) -> None:
        first = {"a::t": 1.0}
        merge_durations([first, {"b::t": 2.0}])
        assert first == {"a::t": 1.0}


class TestLoadDurations:
    def test_reads_node_ids_and_seconds(self, tmp_path: Path) -> None:
        assert load_durations(_write(tmp_path / "d", {"a::t": 1, "b::t": 2.5})) == {
            "a::t": 1.0,
            "b::t": 2.5,
        }

    @pytest.mark.parametrize(
        "payload",
        [[1, 2], {"a::t": "soon"}, {"a::t": True}, {"a::t": -1.0}, {"a::t": None}],
    )
    def test_rejects_a_malformed_map(self, tmp_path: Path, payload: object) -> None:
        with pytest.raises(ValueError):
            load_durations(_write(tmp_path / "d", payload))

    def test_rejects_a_non_finite_value(self, tmp_path: Path) -> None:
        path = tmp_path / "d"
        path.write_text('{"a::t": Infinity}', encoding="utf-8")
        with pytest.raises(ValueError):
            load_durations(path)

    def test_malformed_json_is_a_value_error(self, tmp_path: Path) -> None:
        path = tmp_path / "d"
        path.write_text("{", encoding="utf-8")
        with pytest.raises(ValueError):
            load_durations(path)


class TestMain:
    def test_writes_the_merged_map(self, tmp_path: Path) -> None:
        one = _write(tmp_path / "one.json", {"a::t": 1.0})
        two = _write(tmp_path / "two.json", {"b::t": 2.0})
        out = tmp_path / "out" / "merged.json"
        assert main([str(one), str(two), "--output", str(out)]) == 0
        assert json.loads(out.read_text(encoding="utf-8")) == {"a::t": 1.0, "b::t": 2.0}

    def test_a_missing_input_exits_three_and_writes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "merged.json"
        assert main([str(tmp_path / "absent.json"), "--output", str(out)]) == 3
        assert not out.exists()

    def test_a_malformed_input_exits_two(self, tmp_path: Path) -> None:
        bad = _write(tmp_path / "bad.json", [1])
        assert main([str(bad), "--output", str(tmp_path / "m.json")]) == 2

    def test_an_empty_merge_exits_one_so_an_empty_map_is_never_cached(
        self, tmp_path: Path
    ) -> None:
        empty = _write(tmp_path / "empty.json", {})
        out = tmp_path / "m.json"
        assert main([str(empty), "--output", str(out)]) == 1
        assert not out.exists()

    def test_an_unwritable_output_exits_three(self, tmp_path: Path) -> None:
        one = _write(tmp_path / "one.json", {"a::t": 1.0})
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")
        assert main([str(one), "--output", str(blocker / "m.json")]) == 3

    def test_no_inputs_is_an_argument_error(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--output", str(tmp_path / "m.json")])
        assert exc.value.code == 2
