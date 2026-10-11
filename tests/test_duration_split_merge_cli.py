"""Exit codes and output of the duration split merge CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.testing.duration_split_merge import main
from tests.duration_split_merge_helpers import write_json


class TestMain:
    def test_writes_the_merged_map(self, tmp_path: Path) -> None:
        one = write_json(tmp_path / "one.json", {"a::t": 1.0})
        two = write_json(tmp_path / "two.json", {"b::t": 2.0})
        out = tmp_path / "out" / "merged.json"
        assert main([str(one), str(two), "--output", str(out)]) == 0
        assert json.loads(out.read_text(encoding="utf-8")) == {"a::t": 1.0, "b::t": 2.0}

    def test_a_missing_input_exits_three_and_writes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "merged.json"
        assert main([str(tmp_path / "absent.json"), "--output", str(out)]) == 3
        assert not out.exists()

    def test_a_malformed_input_exits_two(self, tmp_path: Path) -> None:
        bad = write_json(tmp_path / "bad.json", [1])
        assert main([str(bad), "--output", str(tmp_path / "m.json")]) == 2

    def test_an_empty_merge_exits_one_so_an_empty_map_is_never_cached(self, tmp_path: Path) -> None:
        empty = write_json(tmp_path / "empty.json", {})
        out = tmp_path / "m.json"
        assert main([str(empty), "--output", str(out)]) == 1
        assert not out.exists()

    def test_an_unwritable_output_exits_three(self, tmp_path: Path) -> None:
        one = write_json(tmp_path / "one.json", {"a::t": 1.0})
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")
        assert main([str(one), "--output", str(blocker / "m.json")]) == 3

    def test_no_inputs_is_an_argument_error(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--output", str(tmp_path / "m.json")])
        assert exc.value.code == 2
