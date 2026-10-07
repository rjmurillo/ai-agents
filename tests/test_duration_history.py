"""Tests for reading and writing the duration history file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.testing import duration_trend as trend
from scripts.testing.duration_history import load_history
from tests.duration_test_helpers import write_history, write_junit


def _shas(path: Path) -> list[str]:
    return [s["sha"] for s in json.loads(path.read_text(encoding="utf-8"))["snapshots"]]


def test_a_missing_file_is_an_empty_history_with_no_note(tmp_path: Path) -> None:
    assert load_history(tmp_path / "absent.json") == ([], None)
    assert load_history(None) == ([], None)


@pytest.mark.parametrize(
    ("body", "fragment"),
    [("not json", "unreadable"), ('{"schema": 99, "snapshots": []}', "schema 99"),
     ('{"schema": 1}', "unreadable"), ("[]", "unreadable")],
)
def test_a_malformed_history_is_reported_and_treated_as_empty(
    tmp_path: Path, body: str, fragment: str
) -> None:
    path = tmp_path / "history.json"
    path.write_text(body, encoding="utf-8")

    snapshots, note = load_history(path)

    assert snapshots == []
    assert note is not None and fragment in note


def test_write_history_appends_and_keeps_the_newest(tmp_path: Path) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0, 1.0]}, 2.0)
    out = tmp_path / "out.json"

    rc = trend.main([str(report), "--history", str(write_history(tmp_path, [1.0, 2.0, 3.0])),
                     "--write-history", str(out), "--max-history", "2", "--sha", "newest"])

    assert rc == 0
    assert _shas(out) == ["sha2", "newest"]


def test_a_cache_miss_creates_the_output_directory(tmp_path: Path) -> None:
    """The first main run, or one after cache eviction, has no history directory."""
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0]}, 1.0)
    out_dir = tmp_path / "test-durations"
    history = out_dir / "history.json"
    assert not out_dir.exists()

    rc = trend.main([str(report), "--history", str(history), "--write-history", str(history),
                     "--snapshot-out", str(out_dir / "snapshot.json")])

    assert rc == 0
    assert len(_shas(history)) == 1
    assert (out_dir / "snapshot.json").is_file()


def test_history_read_and_written_in_place_keeps_the_old_entries(tmp_path: Path) -> None:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [1.0, 1.0]}, 2.0)
    history = write_history(tmp_path, [1.0, 2.0])

    assert trend.main([str(report), "--history", str(history),
                       "--write-history", str(history), "--sha", "third"]) == 0
    assert _shas(history) == ["sha0", "sha1", "third"]
