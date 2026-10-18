"""Tests for scripts/eval/_human_minutes.py (issue #5768)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._durable_live_test_support import human_mod as hm

ROW = {"control": "reduced", "task_id": "t1", "repeat": 0, "minutes": 4.5}


def _row(**overrides: Any) -> dict[str, Any]:
    return {**ROW, **overrides}


def test_parse_keys_rows_by_cell() -> None:
    cells = hm.parse_human_minutes([ROW, _row(control="current", minutes=0)])

    assert cells == {("reduced", "t1", 0): 4.5, ("current", "t1", 0): 0.0}


def test_zero_minutes_is_a_valid_timed_value() -> None:
    assert hm.parse_human_minutes([_row(minutes=0)])[("reduced", "t1", 0)] == 0.0


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (None, "non-empty JSON array"),
        ([], "non-empty JSON array"),
        ({"control": "x"}, "non-empty JSON array"),
        (["row"], "expected an object"),
        ([{"control": "reduced"}], "missing keys"),
        ([_row(extra=1)], "unknown keys .*extra"),
        ([_row(minutes=-1)], ">= 0"),
        ([_row(minutes=float("nan"))], "finite"),
        ([_row(minutes=float("inf"))], "finite"),
        ([_row(minutes=True)], "must be a number"),
        ([_row(minutes="4")], "must be a number"),
        ([_row(repeat=-1)], "repeat"),
        ([_row(repeat=True)], "repeat"),
        ([_row(repeat=1.0)], "repeat"),
        ([_row(task_id="")], "task_id"),
        ([_row(control=" ")], "control"),
        ([ROW, _row(minutes=9)], "duplicate cell"),
    ],
)
def test_parse_rejects_malformed_rows(raw: object, message: str) -> None:
    with pytest.raises(hm.HumanMinutesError, match=message):
        hm.parse_human_minutes(raw)


def test_parse_rejects_a_control_outside_the_known_set() -> None:
    with pytest.raises(hm.HumanMinutesError, match="not one of"):
        hm.parse_human_minutes([_row(control="other")], known_controls={"full", "reduced"})


def test_load_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "minutes.json"
    path.write_text(json.dumps([ROW]), encoding="utf-8")

    assert hm.load_human_minutes(path) == {("reduced", "t1", 0): 4.5}


def test_load_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(hm.HumanMinutesError, match="cannot read"):
        hm.load_human_minutes(tmp_path / "absent.json")


def test_load_reports_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "minutes.json"
    path.write_text("[{", encoding="utf-8")

    with pytest.raises(hm.HumanMinutesError, match="not valid JSON"):
        hm.load_human_minutes(path)


def test_lookup_returns_none_without_a_row_or_a_file() -> None:
    cells = {("reduced", "t1", 0): 4.5}

    assert hm.lookup(cells, "reduced", "t1", 0) == 4.5
    assert hm.lookup(cells, "reduced", "t1", 1) is None
    assert hm.lookup(None, "reduced", "t1", 0) is None


def test_unmatched_lists_supplied_cells_with_no_record() -> None:
    cells = {("reduced", "t1", 0): 1.0, ("reduced", "t2", 0): 2.0}

    assert hm.unmatched(cells, {("reduced", "t1", 0)}) == [["reduced", "t2", 0]]
    assert hm.unmatched(None, {("reduced", "t1", 0)}) == []
    assert hm.unmatched({}, set()) == []


def test_unmatched_runs_ignores_failed_runs_without_a_record() -> None:
    cells = {("reduced", "t1", 0): 1.0, ("reduced", "t2", 0): 2.0}
    runs = [
        {"control": "reduced", "task_id": "t1", "repeat": 0, "record": {}},
        {"control": "reduced", "task_id": "t2", "repeat": 0, "harness_failure": "boom"},
    ]

    assert hm.unmatched_runs(cells, runs) == [["reduced", "t2", 0]]
