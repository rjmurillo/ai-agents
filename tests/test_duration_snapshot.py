"""Tests for reading JUnit reports into a duration snapshot."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.testing.duration_schema import ids_digest
from scripts.testing.duration_snapshot import Snapshot, build_snapshot, partition_wall_seconds
from tests.duration_test_helpers import NOW, alpha_ids, write_junit


def test_cases_group_by_module_and_partition_records_wall_time(tmp_path: Path) -> None:
    report = write_junit(tmp_path, "pytest-results-bulk",
                         {"tests.test_alpha": [1.5, 2.5], "tests.test_beta": [4.0]}, wall=3.25)

    snap = build_snapshot([report], "abc", NOW)

    assert snap.modules == {
        "tests/test_alpha.py": {"seconds": 4.0, "tests": 2, "ids": alpha_ids(2)},
        "tests/test_beta.py": {"seconds": 4.0, "tests": 1,
                               "ids": ids_digest(["tests/test_beta.py::t0"])},
    }
    assert snap.partitions == {"pytest-results-bulk": {"tests": 3, "wall_seconds": 3.25}}
    assert (snap.total_tests, snap.total_seconds) == (3, 8.0)


def test_a_bare_testsuite_root_reports_its_own_time(tmp_path: Path) -> None:
    path = tmp_path / "bare.xml"
    path.write_text('<testsuite time="7.5"><testcase classname="tests.test_a" '
                    'name="t" time="1" /></testsuite>', encoding="utf-8")

    assert partition_wall_seconds(path) == 7.5


def test_snapshot_round_trips_through_its_dict(tmp_path: Path) -> None:
    snap = build_snapshot([write_junit(tmp_path, "p", {"tests.test_a": [1.0]}, 1.0)], "abc", NOW)

    assert Snapshot.from_dict(json.loads(json.dumps(snap.to_dict()))) == snap


def test_the_ids_digest_ignores_order_and_changes_with_the_test_set() -> None:
    assert ids_digest(["a::x", "a::y"]) == ids_digest(["a::y", "a::x"])
    assert ids_digest(["a::x", "a::y"]) != ids_digest(["a::x", "a::z"])


@pytest.mark.parametrize(
    "entry",
    [{"seconds": "10", "tests": 2, "ids": "d"}, {"seconds": 1.0, "tests": 2.5, "ids": "d"},
     {"seconds": True, "tests": 2, "ids": "d"}, {"seconds": float("nan"), "tests": 2, "ids": "d"},
     {"seconds": -1.0, "tests": 2, "ids": "d"}, {"seconds": 1.0, "tests": 2},
     {"seconds": 1.0, "ids": "d"}, "not an object"],
)
def test_a_malformed_module_entry_is_refused(entry: object) -> None:
    data = {"sha": "s", "recorded_at": "t", "partitions": {}, "modules": {"m": entry}}

    with pytest.raises((ValueError, KeyError)):
        Snapshot.from_dict(data)


@pytest.mark.parametrize("entry", [{"tests": "3", "wall_seconds": 1.0}, ["list"]])
def test_a_malformed_partition_entry_is_refused(entry: object) -> None:
    data = {"sha": "s", "recorded_at": "t", "partitions": {"p": entry}, "modules": {}}

    with pytest.raises(ValueError):
        Snapshot.from_dict(data)
