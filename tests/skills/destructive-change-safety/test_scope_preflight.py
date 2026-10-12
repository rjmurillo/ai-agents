"""Non-destructive scope previews."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
import scope_preflight


def make_db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE parent (id INTEGER PRIMARY KEY);
        CREATE TABLE child (id INTEGER PRIMARY KEY,
            parent_id INTEGER REFERENCES parent(id) ON DELETE CASCADE);
        INSERT INTO parent VALUES (1), (2), (3);
        INSERT INTO child VALUES (10, 1), (11, 1), (12, 2);
        """
    )
    conn.commit()
    conn.close()
    return path


COUNT_QUERIES = {
    "parent": "SELECT COUNT(*) FROM parent",
    "child": "SELECT COUNT(*) FROM child",
}


def row_count(path: Path, table: str) -> int:
    conn = sqlite3.connect(path)
    try:
        return int(conn.execute(COUNT_QUERIES[table]).fetchone()[0])
    finally:
        conn.close()


def test_sql_preview_counts_rows_and_leaves_the_database_unchanged(tmp_path: Path) -> None:
    db = make_db(tmp_path / "app.db")
    before = db.read_bytes()
    result = scope_preflight.preview_sql(db, "DELETE FROM parent WHERE id = 3")
    assert result["count"] == 1
    assert db.read_bytes() == before
    assert row_count(db, "parent") == 3


def test_sql_preview_counts_cascaded_rows_in_total_changes(tmp_path: Path) -> None:
    db = make_db(tmp_path / "app.db")
    result = scope_preflight.preview_sql(db, "DELETE FROM parent WHERE id = 1")
    assert result["count"] == 1
    assert result["total_changes"] == 3
    assert row_count(db, "child") == 3


def test_sql_preview_handles_update(tmp_path: Path) -> None:
    db = make_db(tmp_path / "app.db")
    result = scope_preflight.preview_sql(db, "UPDATE child SET parent_id = 2 WHERE parent_id = 1")
    assert result["count"] == 2


def test_sql_preview_without_where_reports_every_row(tmp_path: Path) -> None:
    db = make_db(tmp_path / "app.db")
    assert scope_preflight.preview_sql(db, "DELETE FROM parent")["count"] == 3


@pytest.mark.parametrize(
    "statement",
    [
        "DROP TABLE parent",
        "SELECT 1",
        "DELETE FROM missing_table",
        "DELETE FROM parent; DELETE FROM child",
    ],
)
def test_sql_preview_refuses_what_it_cannot_measure(tmp_path: Path, statement: str) -> None:
    db = make_db(tmp_path / "app.db")
    with pytest.raises(scope_preflight.PreviewError):
        scope_preflight.preview_sql(db, statement)
    assert row_count(db, "parent") == 3


def test_sql_preview_refuses_a_missing_database(tmp_path: Path) -> None:
    with pytest.raises(scope_preflight.PreviewError, match="not found"):
        scope_preflight.preview_sql(tmp_path / "nope.db", "DELETE FROM parent")


def make_tree(root: Path) -> None:
    (root / "cache").mkdir()
    (root / "cache" / "a.tmp").write_text("a", encoding="utf-8")
    (root / "cache" / "b.tmp").write_text("b", encoding="utf-8")
    (root / "sentinel.txt").write_text("keep", encoding="utf-8")


def test_file_preview_selects_only_matching_files(tmp_path: Path) -> None:
    make_tree(tmp_path)
    result = scope_preflight.preview_files(tmp_path, ["cache/*.tmp"])
    assert result["count"] == 2
    assert result["files"] == ["cache/a.tmp", "cache/b.tmp"]
    assert (tmp_path / "cache" / "a.tmp").exists()


def test_file_cleanup_driven_by_the_preview_spares_the_sentinel(tmp_path: Path) -> None:
    make_tree(tmp_path)
    preview: dict[str, Any] = scope_preflight.preview_files(tmp_path, ["cache/*.tmp"])
    for relative in preview["files"]:
        (tmp_path / relative).unlink()
    assert (tmp_path / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    assert scope_preflight.preview_files(tmp_path, ["cache/*.tmp"])["count"] == 0


def test_file_preview_merges_patterns_without_duplicates(tmp_path: Path) -> None:
    make_tree(tmp_path)
    result = scope_preflight.preview_files(tmp_path, ["cache/*.tmp", "cache/a.*"])
    assert result["count"] == 2


@pytest.mark.parametrize("pattern", ["../*", "/etc/*", "cache/../../*"])
def test_file_preview_refuses_patterns_that_escape_the_root(tmp_path: Path, pattern: str) -> None:
    make_tree(tmp_path)
    with pytest.raises(scope_preflight.PreviewError, match="escapes"):
        scope_preflight.preview_files(tmp_path, [pattern])


def test_file_preview_ignores_symlinks_that_leave_the_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.tmp").write_text("s", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "link.tmp").symlink_to(outside / "secret.tmp")
    assert scope_preflight.preview_files(root, ["*.tmp"])["count"] == 0


def test_file_preview_refuses_a_missing_root(tmp_path: Path) -> None:
    with pytest.raises(scope_preflight.PreviewError, match="not a directory"):
        scope_preflight.preview_files(tmp_path / "gone", ["*"])
