"""CLI boundary tests for build_third_party_gap_corpus.py: input shape and output errors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._third_party_gap_test_support import load_script


@pytest.fixture
def cli() -> Any:
    return load_script("build_third_party_gap_corpus")


def _dump(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "dump.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestDumpShape:
    @pytest.mark.parametrize(
        "payload",
        [
            [],
            {"pull_requests": None, "mined_on": "2026-11-15"},
            {"pull_requests": [1], "mined_on": "2026-11-15"},
            {"pull_requests": [{"number": "1", "baseRefOid": "b"}], "mined_on": "2026-11-15"},
            {"pull_requests": []},
            {"pull_requests": [], "mined_on": "15 Nov"},
        ],
    )
    def test_a_malformed_dump_exits_2(self, cli: Any, tmp_path: Path, payload: object) -> None:
        labels = tmp_path / "labels.jsonl"
        labels.write_text("", encoding="utf-8")

        code = cli.main(["--dump", str(_dump(tmp_path, payload)), "--labels", str(labels)])

        assert code == 2

    def test_the_mining_date_comes_from_the_dump(self, cli: Any) -> None:
        prs, mined_on = cli.validate_dump({"pull_requests": [], "mined_on": "2026-12-01"})

        assert (prs, mined_on) == ([], "2026-12-01")


class TestOutputErrors:
    def test_a_missing_output_directory_is_created(self, cli: Any, tmp_path: Path) -> None:
        out = tmp_path / "new" / "dir"

        code = cli.write({"findings.jsonl": "x\n"}, out, {})

        assert code == 0
        assert (out / "findings.jsonl").read_text(encoding="utf-8") == "x\n"

    def test_an_unwritable_output_exits_2(self, cli: Any, tmp_path: Path) -> None:
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")

        assert cli.write({"findings.jsonl": "x\n"}, blocker / "out", {}) == 2

    def test_an_unreadable_check_target_exits_2(self, cli: Any, tmp_path: Path) -> None:
        (tmp_path / "findings.jsonl").mkdir()

        assert cli.check({"findings.jsonl": "x\n"}, tmp_path) == 2
