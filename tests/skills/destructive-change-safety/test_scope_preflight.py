"""Non-destructive scope previews."""

from __future__ import annotations

import os
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


@pytest.mark.parametrize(
    "name", ["app?mode=rw.db", "app#frag.db", "app%41.db", "app b.db", "app?.db"]
)
def test_sql_preview_reads_the_named_file_when_the_path_holds_uri_characters(
    tmp_path: Path, name: str
) -> None:
    """A ``?``, ``#`` or ``%`` in the path must not retarget the SQLite URI."""
    decoy = make_db(tmp_path / "app.db")
    decoy_alt = make_db(tmp_path / "appA.db")
    target = make_db(tmp_path / name)
    conn = sqlite3.connect(target)
    conn.execute("INSERT INTO parent VALUES (4), (5)")
    conn.commit()
    conn.close()
    decoy_before, alt_before, target_before = (
        decoy.read_bytes(),
        decoy_alt.read_bytes(),
        target.read_bytes(),
    )

    result = scope_preflight.preview_sql(target, "DELETE FROM parent")

    assert result["count"] == 5
    assert (decoy.read_bytes(), decoy_alt.read_bytes(), target.read_bytes()) == (
        decoy_before,
        alt_before,
        target_before,
    )


def test_sql_preview_accepts_a_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_db(tmp_path / "rel.db")
    monkeypatch.chdir(tmp_path)

    assert scope_preflight.preview_sql(Path("rel.db"), "DELETE FROM parent")["count"] == 3


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


def make_nested_tree(root: Path) -> None:
    deep = root / "build" / "sub" / "deeper"
    deep.mkdir(parents=True)
    for index in range(3):
        (root / "build" / f"top{index}.o").write_text("t", encoding="utf-8")
        (deep / f"leaf{index}.o").write_text("l", encoding="utf-8")
    (root / "sentinel.txt").write_text("keep", encoding="utf-8")


@pytest.mark.parametrize("pattern", ["build", "build/", "build/sub", "bui*"])
def test_directory_match_counts_every_file_beneath_it(tmp_path: Path, pattern: str) -> None:
    make_nested_tree(tmp_path)
    result: dict[str, Any] = scope_preflight.preview_files(tmp_path, [pattern])
    assert result["count"] == len(result["files"])
    assert result["count"] > 0
    assert all(name.startswith("build/") for name in result["files"])


def test_bare_directory_pattern_matches_the_recursive_glob(tmp_path: Path) -> None:
    make_nested_tree(tmp_path)
    bare = scope_preflight.preview_files(tmp_path, ["build"])
    recursive = scope_preflight.preview_files(tmp_path, ["build/**"])
    assert bare["count"] == 6
    assert bare["files"] == recursive["files"]


def test_directory_and_file_patterns_merge_without_duplicates(tmp_path: Path) -> None:
    make_nested_tree(tmp_path)
    result = scope_preflight.preview_files(tmp_path, ["build", "build/top0.o"])
    assert result["count"] == 6


def test_directory_match_does_not_select_siblings(tmp_path: Path) -> None:
    make_nested_tree(tmp_path)
    result: dict[str, Any] = scope_preflight.preview_files(tmp_path, ["build/sub"])
    assert result["count"] == 3
    assert "sentinel.txt" not in result["files"]


def test_empty_directory_match_counts_no_files(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    assert scope_preflight.preview_files(tmp_path, ["empty"])["count"] == 0


def test_directory_match_skips_symlinks_that_leave_the_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.o").write_text("s", encoding="utf-8")
    root = tmp_path / "root"
    (root / "build").mkdir(parents=True)
    (root / "build" / "own.o").write_text("o", encoding="utf-8")
    (root / "build" / "file_link.o").symlink_to(outside / "secret.o")
    (root / "build" / "dir_link").symlink_to(outside, target_is_directory=True)
    result: dict[str, Any] = scope_preflight.preview_files(root, ["build"])
    assert result["files"] == ["build/own.o"]


def test_matched_directory_symlink_that_leaves_the_root_is_ignored(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.o").write_text("s", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "build").symlink_to(outside, target_is_directory=True)
    assert scope_preflight.preview_files(root, ["build"])["count"] == 0


def test_unreadable_subdirectory_fails_closed(tmp_path: Path) -> None:
    make_nested_tree(tmp_path)
    locked = tmp_path / "build" / "sub"
    locked.chmod(0)
    try:
        if os.access(locked, os.R_OK):
            pytest.skip("directory permissions are not enforced for this user")
        with pytest.raises(scope_preflight.PreviewError, match="cannot read directory"):
            scope_preflight.preview_files(tmp_path, ["build"])
    finally:
        locked.chmod(0o755)
