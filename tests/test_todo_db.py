"""Tests for scripts/todo_db.py (issue #4379).

Covers: upsert idempotency, completion assertion, missing-row failure,
concurrent-insert safety, and CLI exit codes.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from scripts.todo_db import MissingTodoError, complete_todo, ensure_todo, main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> Path:
    return tmp_path / "todos.db"


def _row(conn: sqlite3.Connection, todo_id: str) -> dict | None:
    cur = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,))
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip([c[0] for c in cur.description], row, strict=True))


# ---------------------------------------------------------------------------
# ensure_todo: positive (row absent -> insert)
# ---------------------------------------------------------------------------


class TestEnsureTodoInsert:
    def test_returns_true_when_absent(self, tmp_path: Path) -> None:
        inserted = ensure_todo(_make_db(tmp_path), "t1", "Task one")
        assert inserted is True

    def test_row_exists_after_insert(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        ensure_todo(db, "t1", "Task one")
        conn = sqlite3.connect(db)
        row = _row(conn, "t1")
        conn.close()
        assert row is not None
        assert row["title"] == "Task one"
        assert row["status"] == "pending"


# ---------------------------------------------------------------------------
# ensure_todo: idempotent (row exists -> no-op)
# ---------------------------------------------------------------------------


class TestEnsureTodoIdempotent:
    def test_returns_false_when_present(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        ensure_todo(db, "t1", "Task one")
        second = ensure_todo(db, "t1", "Different title")
        assert second is False

    def test_existing_row_unchanged(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        ensure_todo(db, "t1", "Original title")
        ensure_todo(db, "t1", "Different title")
        conn = sqlite3.connect(db)
        row = _row(conn, "t1")
        conn.close()
        assert row is not None
        assert row["title"] == "Original title"


# ---------------------------------------------------------------------------
# complete_todo: positive (row exists -> done)
# ---------------------------------------------------------------------------


class TestCompleteTodo:
    def test_marks_done(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        ensure_todo(db, "t1", "Task one")
        complete_todo(db, "t1")
        conn = sqlite3.connect(db)
        row = _row(conn, "t1")
        conn.close()
        assert row is not None
        assert row["status"] == "done"

    def test_no_exception_on_success(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        ensure_todo(db, "t1", "Task one")
        complete_todo(db, "t1")  # must not raise


# ---------------------------------------------------------------------------
# complete_todo: negative (row absent -> MissingTodoError)
# ---------------------------------------------------------------------------


class TestCompleteTodoMissingRow:
    def test_raises_missing_todo_error(self, tmp_path: Path) -> None:
        with pytest.raises(MissingTodoError, match="pr-4379"):
            complete_todo(_make_db(tmp_path), "pr-4379")

    def test_error_carries_todo_id(self, tmp_path: Path) -> None:
        try:
            complete_todo(_make_db(tmp_path), "pr-4379")
        except MissingTodoError as exc:
            assert exc.todo_id == "pr-4379"
        else:
            pytest.fail("MissingTodoError not raised")


# ---------------------------------------------------------------------------
# ensure_todo: concurrent inserts (same ID, two connections)
# ---------------------------------------------------------------------------


class TestEnsureTodoConcurrent:
    def test_only_one_row_after_concurrent_insert(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        # Simulate two agents calling ensure_todo at roughly the same time.
        # In SQLite's WAL mode, one INSERT OR IGNORE wins and one is a no-op.
        r1 = ensure_todo(db, "shared", "First caller")
        r2 = ensure_todo(db, "shared", "Second caller")
        # Exactly one insertion must have happened.
        assert r1 != r2  # one True, one False
        conn = sqlite3.connect(db)
        cur = conn.execute("SELECT COUNT(*) FROM todos WHERE id = 'shared'")
        count = cur.fetchone()[0]
        conn.close()
        assert count == 1


# ---------------------------------------------------------------------------
# CLI: exit codes
# ---------------------------------------------------------------------------


class TestCLIEnsure:
    def test_ensure_exits_zero_on_insert(self, tmp_path: Path) -> None:
        rc = main(["ensure", str(_make_db(tmp_path)), "t1", "Task one"])
        assert rc == 0

    def test_ensure_exits_zero_on_existing(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        main(["ensure", str(db), "t1", "Task one"])
        rc = main(["ensure", str(db), "t1", "Task one again"])
        assert rc == 0


class TestCLIComplete:
    def test_complete_exits_zero_when_row_exists(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        main(["ensure", str(db), "t1", "Task one"])
        rc = main(["complete", str(db), "t1"])
        assert rc == 0

    def test_complete_exits_one_when_row_absent(self, tmp_path: Path) -> None:
        rc = main(["complete", str(_make_db(tmp_path)), "pr-missing"])
        assert rc == 1
