"""Each overlapping pre-push lane gets its own testmon database (issue #6477).

The shared database let one lane's writes change what another lane's xdist
workers read while they collected, so the workers deselected different tests.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from scripts.validation import testmon_lane_db

BASE = ".testmondata"


def _finished(path: Path, rows: tuple[str, ...] = ()) -> None:
    """Write a database like testmon leaves it: tables, rows, user_version set."""
    with closing(sqlite3.connect(path)) as database:
        database.execute("CREATE TABLE IF NOT EXISTS marker (name TEXT)")
        database.executemany("INSERT INTO marker VALUES (?)", [(row,) for row in rows])
        database.execute("PRAGMA user_version = 1")
        database.commit()


def _rows(path: Path) -> list[str]:
    with closing(sqlite3.connect(path)) as database:
        return [row[0] for row in database.execute("SELECT name FROM marker ORDER BY name")]


def test_each_lane_gets_a_distinct_name_next_to_the_base() -> None:
    names = [testmon_lane_db.lane_datafile(BASE, index) for index in range(3)]

    assert names == [".testmondata-lane0", ".testmondata-lane1", ".testmondata-lane2"]
    assert len(set(names)) == 3


def test_a_relocated_base_keeps_its_lane_files_beside_it() -> None:
    assert testmon_lane_db.lane_datafile("cache/tm.db", 1) == "cache/tm.db-lane1"


def test_every_lane_starts_as_a_copy_of_the_base(tmp_path: Path) -> None:
    _finished(tmp_path / BASE, ("a", "b"))

    names = testmon_lane_db.prepare_lane_datafiles(tmp_path, BASE, 3)

    assert len(names) == 3
    for name in names:
        assert _rows(tmp_path / name) == ["a", "b"]
    assert _rows(tmp_path / BASE) == ["a", "b"]


def test_lane_copies_are_independent_files(tmp_path: Path) -> None:
    _finished(tmp_path / BASE, ("a",))
    names = testmon_lane_db.prepare_lane_datafiles(tmp_path, BASE, 2)

    with closing(sqlite3.connect(tmp_path / names[0])) as database:
        database.execute("INSERT INTO marker VALUES ('only-lane-0')")
        database.commit()

    assert _rows(tmp_path / names[0]) == ["a", "only-lane-0"]
    assert _rows(tmp_path / names[1]) == ["a"]
    assert _rows(tmp_path / BASE) == ["a"]


def test_a_copy_includes_rows_that_only_the_wal_file_holds(tmp_path: Path) -> None:
    base = tmp_path / BASE
    _finished(base, ("checkpointed",))
    writer = sqlite3.connect(base)
    try:
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute("PRAGMA wal_autocheckpoint = 0")
        writer.execute("INSERT INTO marker VALUES ('in-wal')")
        writer.commit()
        names = testmon_lane_db.prepare_lane_datafiles(tmp_path, BASE, 1)
    finally:
        writer.close()

    assert _rows(tmp_path / names[0]) == ["checkpointed", "in-wal"]


def test_a_finished_lane_database_is_kept(tmp_path: Path) -> None:
    _finished(tmp_path / BASE, ("from-base",))
    _finished(tmp_path / ".testmondata-lane0", ("lane-history",))

    names = testmon_lane_db.prepare_lane_datafiles(tmp_path, BASE, 2)

    assert _rows(tmp_path / names[0]) == ["lane-history"]
    assert _rows(tmp_path / names[1]) == ["from-base"]


def test_an_interrupted_lane_database_is_replaced_by_a_fresh_copy(tmp_path: Path) -> None:
    _finished(tmp_path / BASE, ("from-base",))
    with closing(sqlite3.connect(tmp_path / ".testmondata-lane0")) as database:
        database.execute("CREATE TABLE half (x TEXT)")

    names = testmon_lane_db.prepare_lane_datafiles(tmp_path, BASE, 1)

    assert _rows(tmp_path / names[0]) == ["from-base"]


def test_a_corrupt_lane_database_is_replaced_by_a_fresh_copy(tmp_path: Path) -> None:
    _finished(tmp_path / BASE, ("from-base",))
    (tmp_path / ".testmondata-lane0").write_bytes(b"not a sqlite file")

    names = testmon_lane_db.prepare_lane_datafiles(tmp_path, BASE, 1)

    assert _rows(tmp_path / names[0]) == ["from-base"]


def test_without_a_finished_base_no_lane_file_is_created(tmp_path: Path) -> None:
    names = testmon_lane_db.prepare_lane_datafiles(tmp_path, BASE, 2)

    assert names == [".testmondata-lane0", ".testmondata-lane1"]
    assert not any((tmp_path / name).exists() for name in names)


def test_an_unfinished_base_is_not_copied(tmp_path: Path) -> None:
    with closing(sqlite3.connect(tmp_path / BASE)) as database:
        database.execute("CREATE TABLE half (x TEXT)")

    names = testmon_lane_db.prepare_lane_datafiles(tmp_path, BASE, 1)

    assert not (tmp_path / names[0]).exists()


def test_a_failed_copy_leaves_no_lane_file_and_no_staging_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _finished(tmp_path / BASE, ("a",))

    def fail(_source: Path, _target: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(testmon_lane_db, "_copy_database", fail)

    names = testmon_lane_db.prepare_lane_datafiles(tmp_path, BASE, 1)

    assert not (tmp_path / names[0]).exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == [BASE]


def test_a_copy_that_fails_midway_removes_its_staging_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _finished(tmp_path / BASE, ("a",))

    def refuse(_source: object, _target: object) -> None:
        raise OSError("rename refused")

    monkeypatch.setattr(testmon_lane_db.os, "replace", refuse)

    names = testmon_lane_db.prepare_lane_datafiles(tmp_path, BASE, 1)

    assert not (tmp_path / names[0]).exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == [BASE]


def test_zero_lanes_prepare_nothing(tmp_path: Path) -> None:
    _finished(tmp_path / BASE)

    assert testmon_lane_db.prepare_lane_datafiles(tmp_path, BASE, 0) == []


def test_database_finished_follows_user_version(tmp_path: Path) -> None:
    path = tmp_path / BASE
    assert testmon_lane_db.database_finished(path) is False
    with closing(sqlite3.connect(path)) as database:
        database.execute("CREATE TABLE t (x TEXT)")
    assert testmon_lane_db.database_finished(path) is False
    _finished(path)
    assert testmon_lane_db.database_finished(path) is True
