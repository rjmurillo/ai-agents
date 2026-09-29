"""Tests for scripts/todo_db.py (issue #4379).

Covers: upsert idempotency, status assertion for every status, missing-row
and duplicate-row failure with rollback, concurrent-caller safety, and CLI
exit codes.
"""

from __future__ import annotations

import sqlite3
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from scripts.todo_db import (
    TODO_STATUSES,
    DuplicateTodoError,
    MissingTodoError,
    complete_todo,
    ensure_todo,
    main,
    set_todo_status,
)

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


def _count(db: Path, todo_id: str) -> int:
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT COUNT(*) FROM todos WHERE id = ?", (todo_id,)).fetchone()[0]
    finally:
        conn.close()


def _status(db: Path, todo_id: str) -> str | None:
    conn = sqlite3.connect(db)
    try:
        row = _row(conn, todo_id)
    finally:
        conn.close()
    return None if row is None else row["status"]


def _race(workers: int, call) -> list:
    """Run ``call`` on ``workers`` threads released together; return results."""
    barrier = threading.Barrier(workers)
    results: list = [None] * workers
    errors: list[BaseException] = []

    def run(index: int) -> None:
        barrier.wait()
        try:
            results[index] = call()
        except BaseException as exc:  # surfaced to the test below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    return results


def _no_key_connection(rows: list[tuple[str, str]]) -> sqlite3.Connection:
    """Open a todos table without a primary key, as an external tool might."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE todos (id TEXT, title TEXT, status TEXT)")
    conn.executemany("INSERT INTO todos (id, title, status) VALUES (?, ?, 'pending')", rows)
    conn.commit()
    return conn


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
    def test_only_one_row_after_sequential_insert(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        r1 = ensure_todo(db, "shared", "First caller")
        r2 = ensure_todo(db, "shared", "Second caller")
        assert r1 != r2  # one True, one False
        assert _count(db, "shared") == 1

    def test_only_one_insert_across_threads(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        ensure_todo(db, "seed", "Create the schema before the race")
        results = _race(8, lambda: ensure_todo(db, "shared", "Racing caller"))
        assert sorted(results) == [False] * 7 + [True]
        assert _count(db, "shared") == 1

    def test_concurrent_status_updates_each_affect_one_row(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        ensure_todo(db, "shared", "Shared task")
        results = _race(8, lambda: set_todo_status(db, "shared", "in_progress"))
        assert results == [None] * 8
        assert _status(db, "shared") == "in_progress"


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


class TestCLIStatus:
    @pytest.mark.parametrize("status", TODO_STATUSES)
    def test_status_exits_zero_and_records(
        self, tmp_path: Path, status: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = _make_db(tmp_path)
        main(["ensure", str(db), "t1", "Task one"])
        rc = main(["status", str(db), "t1", status])
        assert rc == 0
        assert _status(db, "t1") == status
        assert capsys.readouterr().out.strip().endswith(f"{status}: t1")

    def test_status_exits_one_when_row_absent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(["status", str(_make_db(tmp_path)), "pr-4298", "blocked"])
        assert rc == 1
        assert "pr-4298" in capsys.readouterr().err

    def test_status_exits_one_on_duplicate_rows(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE todos (id TEXT, title TEXT, status TEXT)")
        conn.executemany(
            "INSERT INTO todos VALUES (?, ?, 'pending')",
            [("dup", "a"), ("dup", "b")],
        )
        conn.commit()
        conn.close()
        rc = main(["status", str(db), "dup", "done"])
        assert rc == 1
        conn = sqlite3.connect(db)
        statuses = [r[0] for r in conn.execute("SELECT status FROM todos")]
        conn.close()
        assert statuses == ["pending", "pending"]

    def test_status_rejects_unknown_status(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["status", str(_make_db(tmp_path)), "t1", "finished"])
        assert exc.value.code == 2

    def test_sqlite_failure_exits_three(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(["ensure", str(tmp_path), "t1", "Directory is not a database"])
        assert rc == 3
        assert "sqlite failure for todo 't1'" in capsys.readouterr().err

    def test_ensure_prints_created_then_exists(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = _make_db(tmp_path)
        main(["ensure", str(db), "t1", "Task one"])
        main(["ensure", str(db), "t1", "Task one"])
        assert capsys.readouterr().out.split() == ["created:", "t1", "exists:", "t1"]


class TestSetTodoStatus:
    @pytest.mark.parametrize("status", TODO_STATUSES)
    def test_records_each_status(self, tmp_path: Path, status: str) -> None:
        db = _make_db(tmp_path)
        ensure_todo(db, "t1", "Task one")
        set_todo_status(db, "t1", status)
        assert _status(db, "t1") == status

    def test_rejects_unknown_status_without_writing(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        ensure_todo(db, "t1", "Task one")
        with pytest.raises(ValueError, match="finished"):
            set_todo_status(db, "t1", "finished")
        assert _status(db, "t1") == "pending"

    def test_missing_row_raises_and_creates_nothing(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        with pytest.raises(MissingTodoError) as exc:
            set_todo_status(db, "pr-4298", "blocked")
        assert exc.value.rowcount == 0
        assert _count(db, "pr-4298") == 0

    def test_duplicate_rows_raise_and_roll_back(self) -> None:
        conn = _no_key_connection([("dup", "a"), ("dup", "b"), ("other", "c")])
        with pytest.raises(DuplicateTodoError) as exc:
            set_todo_status(conn, "dup", "done")
        assert exc.value.todo_id == "dup"
        assert exc.value.rowcount == 2
        statuses = [r[0] for r in conn.execute("SELECT status FROM todos")]
        assert statuses == ["pending", "pending", "pending"]
        assert conn.in_transaction is False
        conn.close()

    def test_recovery_path_for_assigned_but_missing_todo(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        with pytest.raises(MissingTodoError):
            complete_todo(db, "pr-4298")
        assert ensure_todo(db, "pr-4298", "Recovered assignment") is True
        complete_todo(db, "pr-4298")
        assert _status(db, "pr-4298") == "done"


class TestEnsureTodoWithConnection:
    def test_inserts_through_caller_connection(self) -> None:
        conn = _no_key_connection([])
        assert ensure_todo(conn, "t1", "Task one") is True
        assert ensure_todo(conn, "t1", "Task one") is False
        assert conn.execute("SELECT COUNT(*) FROM todos").fetchone()[0] == 1
        conn.close()

    def test_duplicate_rows_raise_without_inserting(self) -> None:
        conn = _no_key_connection([("dup", "a"), ("dup", "b")])
        with pytest.raises(DuplicateTodoError) as exc:
            ensure_todo(conn, "dup", "Third copy")
        assert exc.value.rowcount == 2
        assert conn.execute("SELECT COUNT(*) FROM todos").fetchone()[0] == 2
        conn.close()

    def test_rejects_connection_with_open_transaction(self) -> None:
        conn = _no_key_connection([("t1", "a")])
        conn.execute("INSERT INTO todos VALUES ('t2', 'b', 'pending')")
        assert conn.in_transaction is True
        with pytest.raises(ValueError, match="open transaction"):
            ensure_todo(conn, "t3", "Task three")
        with pytest.raises(ValueError, match="open transaction"):
            set_todo_status(conn, "t1", "done")
        conn.rollback()
        conn.close()
