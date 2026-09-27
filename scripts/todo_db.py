"""Safe todo-row management for orchestrated tasks (issue #4379).

An orchestrated task can be assigned a todo ID that does not yet exist in the
session database. A bare ``UPDATE todos SET status = 'done' WHERE id = ?``
returns ``changes() = 0`` and silently discards the outcome.

This module provides three entry-points:

- ``ensure_todo(db, todo_id, title)`` -- idempotent upsert: creates the row if
  absent, leaves it unchanged if it already exists. Returns True if it was
  inserted, False if it already existed. This is also the recovery path for
  an assigned-but-missing todo.
- ``set_todo_status(db, todo_id, status)`` -- records ``pending``,
  ``in_progress``, ``done``, or ``blocked`` and asserts exactly one row was
  affected. Zero rows raises ``MissingTodoError``; more than one raises
  ``DuplicateTodoError``. Either failure rolls the update back.
- ``complete_todo(db, todo_id)`` -- shorthand for ``set_todo_status(..., 'done')``.

Each accepts a path (``str | Path``) or an open ``sqlite3.Connection``. A
passed connection must not hold an open transaction; each call runs its own
``BEGIN IMMEDIATE`` transaction so concurrent callers serialize on the write
lock instead of racing between a read and a write.

CLI usage (for agents calling from a shell)::

    uv run --frozen python scripts/todo_db.py ensure <db-path> <todo-id> <title>
    uv run --frozen python scripts/todo_db.py status <db-path> <todo-id> <status>
    uv run --frozen python scripts/todo_db.py complete <db-path> <todo-id>

Exit codes: 0 = success, 1 = logic error (missing or duplicate row),
2 = config error (bad arguments), 3 = external error (SQLite failure).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

TODO_STATUSES: tuple[str, ...] = ("pending", "in_progress", "done", "blocked")

_DB_SCHEMA = """\
CREATE TABLE IF NOT EXISTS todos (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT,
    updated_at TEXT
);
"""


class TodoRowCountError(RuntimeError):
    """Raised when an operation needs exactly one todo row and found another count."""

    def __init__(self, todo_id: str, rowcount: int, message: str) -> None:
        super().__init__(message)
        self.todo_id = todo_id
        self.rowcount = rowcount


class MissingTodoError(TodoRowCountError):
    """Raised when a todo row is absent and the operation requires it."""

    def __init__(self, todo_id: str) -> None:
        super().__init__(
            todo_id, 0, f"todo row '{todo_id}' not found; run ensure (ensure_todo) first"
        )


class DuplicateTodoError(TodoRowCountError):
    """Raised when more than one row carries the same todo ID."""

    def __init__(self, todo_id: str, rowcount: int) -> None:
        super().__init__(
            todo_id,
            rowcount,
            f"todo id '{todo_id}' matched {rowcount} rows; expected exactly 1",
        )


@contextmanager
def _open_db(
    db: str | Path | sqlite3.Connection,
) -> Generator[sqlite3.Connection, None, None]:
    if isinstance(db, sqlite3.Connection):
        yield db
        return
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_DB_SCHEMA)
        yield conn
    finally:
        conn.close()


@contextmanager
def _write_transaction(conn: sqlite3.Connection) -> Generator[None, None, None]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.rollback()
        raise
    conn.commit()


def _require_one_row(todo_id: str, rowcount: int) -> None:
    if rowcount == 0:
        raise MissingTodoError(todo_id)
    if rowcount > 1:
        raise DuplicateTodoError(todo_id, rowcount)


def ensure_todo(
    db: str | Path | sqlite3.Connection,
    todo_id: str,
    title: str,
) -> bool:
    """Create the todo row if absent; leave it unchanged if present.

    Returns True when a new row was inserted, False when the row already
    existed (either state is success for the caller). Raises
    ``DuplicateTodoError`` when the table already holds more than one row for
    ``todo_id``, which can happen in a table created without a primary key.

    The existence check and the insert share one ``BEGIN IMMEDIATE``
    transaction, so a concurrent call with the same todo_id observes one
    insertion and one no-op.
    """
    with _open_db(db) as conn, _write_transaction(conn):
        (count,) = conn.execute("SELECT COUNT(*) FROM todos WHERE id = ?", (todo_id,)).fetchone()
        if count > 1:
            raise DuplicateTodoError(todo_id, count)
        if count == 1:
            return False
        conn.execute(
            "INSERT INTO todos (id, title, status) VALUES (?, ?, 'pending')",
            (todo_id, title),
        )
        return True


def set_todo_status(
    db: str | Path | sqlite3.Connection,
    todo_id: str,
    status: str,
) -> None:
    """Record a todo status and assert exactly one row was affected.

    Raises ``ValueError`` for a status outside ``TODO_STATUSES``,
    ``MissingTodoError`` when the row is absent, and ``DuplicateTodoError``
    when more than one row matched. A failed assertion rolls the update back,
    so callers get a structured failure instead of a silent zero-row UPDATE.
    """
    if status not in TODO_STATUSES:
        raise ValueError(
            f"unknown todo status '{status}'; expected one of {', '.join(TODO_STATUSES)}"
        )
    with _open_db(db) as conn, _write_transaction(conn):
        cur = conn.execute(
            "UPDATE todos SET status = ? WHERE id = ?",
            (status, todo_id),
        )
        _require_one_row(todo_id, cur.rowcount)


def complete_todo(
    db: str | Path | sqlite3.Connection,
    todo_id: str,
) -> None:
    """Mark a todo done; see ``set_todo_status`` for the failure contract."""
    set_todo_status(db, todo_id, "done")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe todo-row management for orchestrated tasks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ensure = sub.add_parser("ensure", help="Upsert a todo row")
    ensure.add_argument("db_path", help="Path to the SQLite database file")
    ensure.add_argument("todo_id", help="Todo identifier (primary key)")
    ensure.add_argument("title", help="Human-readable title for the todo")

    status = sub.add_parser("status", help="Record a todo status (asserts exactly one row)")
    status.add_argument("db_path", help="Path to the SQLite database file")
    status.add_argument("todo_id", help="Todo identifier to update")
    status.add_argument("status", choices=TODO_STATUSES, help="New status")

    complete = sub.add_parser("complete", help="Mark a todo done (asserts row exists)")
    complete.add_argument("db_path", help="Path to the SQLite database file")
    complete.add_argument("todo_id", help="Todo identifier to mark done")

    return parser


def _run(args: argparse.Namespace) -> str:
    if args.command == "ensure":
        inserted = ensure_todo(args.db_path, args.todo_id, args.title)
        return f"{'created' if inserted else 'exists'}: {args.todo_id}"
    status = "done" if args.command == "complete" else args.status
    set_todo_status(args.db_path, args.todo_id, status)
    return f"{status}: {args.todo_id}"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        print(_run(args))
    except TodoRowCountError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:
        print(f"error: sqlite failure for todo '{args.todo_id}': {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
