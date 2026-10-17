#!/usr/bin/env python3
"""Non-destructive scope previews (destructive-change-safety).

``preview_files`` lists what a glob would touch under a root, counting the
files beneath any directory the glob matches. ``preview_sql``
runs one SQLite DELETE or UPDATE against an in-memory copy of the database and
reports the rows it changed. Neither writes to the target. A preview that
cannot run raises ``PreviewError``; the caller reports unknown scope, which the
gate blocks.

EXIT CODES (ADR-035), through ``destructive_gate.py``:
    0 - Preview produced a count
    1 - Preview refused or failed: scope is unknown
    2 - Config error: bad arguments
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

SQL_VERBS = re.compile(r"^\s*(DELETE|UPDATE)\b", re.IGNORECASE)


class PreviewError(Exception):
    """The scope could not be measured without risk."""


def _raise_walk_error(error: OSError) -> None:
    """Fail closed: an unreadable subdirectory leaves part of the scope unmeasured."""
    raise PreviewError(f"cannot read directory while counting: {error}") from error


def _files_beneath(directory: Path) -> list[Path]:
    """Return every file under ``directory`` without following directory symlinks."""
    found: list[Path] = []
    for current, _dirs, names in os.walk(directory, onerror=_raise_walk_error):
        found.extend(Path(current) / name for name in names)
    return found


def _selected_files(item: Path, base: Path) -> list[Path]:
    """Return the files a glob match selects: itself, or all files under a directory."""
    if not item.resolve().is_relative_to(base):
        return []
    if item.is_dir():
        return _files_beneath(item)
    return [item] if item.is_file() else []


def preview_files(root: Path, patterns: list[str]) -> dict[str, object]:
    """Return the files under ``root`` that ``patterns`` select, never touching them.

    A pattern that matches a directory selects every file beneath it, because
    removing the directory removes them all. Symlinks that leave the root are
    ignored.
    """
    if not root.is_dir():
        raise PreviewError(f"root is not a directory: {root}")
    base = root.resolve()
    selected: set[str] = set()
    for pattern in patterns:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise PreviewError(f"pattern escapes the root: {pattern}")
        for item in base.glob(pattern):
            for path in _selected_files(item, base):
                if path.resolve().is_relative_to(base):
                    selected.add(path.relative_to(base).as_posix())
    files = sorted(selected)
    return {"kind": "files", "root": str(base), "count": len(files), "files": files}


def preview_sql(database: Path, statement: str) -> dict[str, object]:
    """Run one DELETE or UPDATE on an in-memory copy and report the rows changed."""
    if not SQL_VERBS.match(statement):
        raise PreviewError("only a single DELETE or UPDATE statement can be previewed")
    if not database.is_file():
        raise PreviewError(f"database file not found: {database}")
    source = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    copy = sqlite3.connect(":memory:")
    try:
        source.backup(copy)
        copy.execute("PRAGMA foreign_keys = ON")
        before = copy.total_changes
        cursor = copy.execute(statement)
        return {
            "kind": "sql",
            "count": cursor.rowcount,
            "total_changes": copy.total_changes - before,
        }
    except sqlite3.Error as error:
        raise PreviewError(f"preview failed: {error}") from error
    finally:
        source.close()
        copy.close()
