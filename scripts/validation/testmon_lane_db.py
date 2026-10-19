"""Give each overlapping pre-push pytest lane its own testmon database (issue #6477).

The pre-push lanes run at the same time. When they shared one ``.testmondata``,
a lane that finished recording its tests changed the file fingerprints that the
workers of another lane read while they collected. Two xdist workers then saw a
different "changed files" set (25 against 35 in the logged run), deselected
different tests, and xdist stopped with "Different tests were collected".

Each lane now reads and writes ``<base>-lane<N>``. The partitions hold disjoint
tests, so the lane databases never need merging. A lane database that is
missing or unfinished starts as a copy of the base database, which is main's
seed or the database a sequential run built. A finished lane database is kept,
so later pushes select from what that lane recorded.

The base database is not updated by overlapped runs. A later sequential run
selects from it and so may re-run tests a lane already recorded, which costs
time and never skips a test.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

LANE_SUFFIX = "-lane"


def lane_datafile(base_name: str, index: int) -> str:
    """Return the data file name for lane ``index``, next to the base database."""
    return f"{base_name}{LANE_SUFFIX}{index}"


def database_finished(path: Path) -> bool:
    """Whether ``path`` is a database testmon finished building.

    testmon sets ``PRAGMA user_version`` after it creates every table, so a file
    whose version is still 0 is an interrupted build. An unreadable file is not
    finished either.
    """
    if not path.exists():
        return False
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as database:
            return int(database.execute("PRAGMA user_version").fetchone()[0]) != 0
    except sqlite3.Error:
        return False


def _clear(path: Path) -> None:
    """Remove a database file and its sidecars so a copy starts clean."""
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def _copy_database(source: Path, target: Path) -> None:
    """Copy ``source`` to ``target`` through SQLite's backup API.

    A plain file copy would miss rows that still sit in the source's WAL file.
    The copy lands under a temporary name and is renamed into place, so a lane
    never sees a half-written database that already looks finished.
    """
    staging = target.with_name(f"{target.name}.copy-{os.getpid()}")
    _clear(staging)
    try:
        source_uri = f"{source.resolve().as_uri()}?mode=ro"
        with (
            closing(sqlite3.connect(source_uri, uri=True)) as src,
            closing(sqlite3.connect(staging)) as dst,
        ):
            src.backup(dst)
        _clear(target)
        os.replace(staging, target)
    finally:
        _clear(staging)


def prepare_lane_datafiles(repo_root: Path, base_name: str, lane_count: int) -> list[str]:
    """Return one data file name per lane, creating the ones that need a seed.

    ``base_name`` is relative to ``repo_root``, the same rule testmon uses. A
    lane whose database is already finished is left alone. When the copy
    fails, the lane keeps no file and testmon builds its own, which runs the
    lane's tests in full and never skips one.
    """
    base = repo_root / base_name
    names = [lane_datafile(base_name, index) for index in range(lane_count)]
    for name in names:
        lane = repo_root / name
        if database_finished(lane) or not database_finished(base):
            continue
        try:
            _copy_database(base, lane)
        except (sqlite3.Error, OSError):
            _clear(lane)
    return names
