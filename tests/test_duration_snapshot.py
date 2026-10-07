"""Tests for reading JUnit reports into a duration snapshot."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.testing.duration_snapshot import Snapshot, build_snapshot, partition_wall_seconds
from tests.duration_test_helpers import NOW, write_junit


def test_cases_group_by_module_and_partition_records_wall_time(tmp_path: Path) -> None:
    report = write_junit(tmp_path, "pytest-results-bulk",
                         {"tests.test_alpha": [1.5, 2.5], "tests.test_beta": [4.0]}, wall=3.25)

    snap = build_snapshot([report], "abc", NOW)

    assert snap.modules == {
        "tests/test_alpha.py": {"seconds": 4.0, "tests": 2},
        "tests/test_beta.py": {"seconds": 4.0, "tests": 1},
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
