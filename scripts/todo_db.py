"""Safe todo-row management for orchestrated tasks (issue #4379).

An orchestrated task can be assigned a todo ID that does not yet exist in the
session database. A bare ``UPDATE todos SET status = 'done' WHERE id = ?``
returns ``changes() = 0`` and silently discards the outcome.

This module provides two entry-points:

- ``ensure_todo(db, todo_id, title)`` -- idempotent upsert: creates the row if
  absent, leaves it unchanged if it already exists. Returns True if it was
  inserted, False if it already existed.
- ``complete_todo(db, todo_id)`` -- marks a row done and asserts exactly one
  row was affected. Raises ``MissingTodoError`` when the row is absent.

Both accept a path (``str | Path``) or an open ``sqlite3.Connection``.

CLI usage (for agents calling from a shell)::

    uv run --frozen python scripts/todo_db.py ensure <db-path> <todo-id> <title>
    uv run --frozen python scripts/todo_db.py complete <db-path> <todo-id>

Exit codes: 0 = success, 1 = logic error (missing row), 2 = config error
(bad arguments).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

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


class MissingTodoError(RuntimeError):
    """Raised when a todo row is absent and the operation requires it."""

    def __init__(self, todo_id: str) -> None:
        super().__init__(f"todo row '{todo_id}' not found; run ensure_todo first")
        self.todo_id = todo_id


@contextmanager
def _open_db(
    db: str | Path | sqlite3.Connection,
) -> Generator[sqlite3.Connection, None, None]:
    if isinstance(db, sqlite3.Connection):
        yield db
        return
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        conn.executescript(_DB_SCHEMA)
        yield conn
    finally:
        conn.close()


def ensure_todo(
    db: str | Path | sqlite3.Connection,
    todo_id: str,
    title: str,
) -> bool:
    """Create the todo row if absent; leave it unchanged if present.

    Returns True when a new row was inserted, False when the row already
    existed (either state is success for the caller).

    Thread-safety: the INSERT OR IGNORE is atomic inside SQLite's WAL mode, so
    a concurrent call with the same todo_id will observe one insertion and
    one no-op.
    """
    with _open_db(db) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO todos (id, title, status) VALUES (?, ?, 'pending')",
            (todo_id, title),
        )
        conn.commit()
        return cur.rowcount == 1


def complete_todo(
    db: str | Path | sqlite3.Connection,
    todo_id: str,
) -> None:
    """Mark a todo done and assert exactly one row was affected.

    Raises ``MissingTodoError`` when the row is absent so callers get a clear
    structured failure instead of a silent zero-row UPDATE.
    """
    with _open_db(db) as conn:
        cur = conn.execute(
            "UPDATE todos SET status = 'done' WHERE id = ?",
            (todo_id,),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise MissingTodoError(todo_id)
        if cur.rowcount > 1:
            raise RuntimeError(  # pragma: no cover -- id is PRIMARY KEY
                f"UPDATE affected {cur.rowcount} rows for todo '{todo_id}'; "
                "expected exactly 1. Database may be corrupt."
            )


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

    complete = sub.add_parser("complete", help="Mark a todo done (asserts row exists)")
    complete.add_argument("db_path", help="Path to the SQLite database file")
    complete.add_argument("todo_id", help="Todo identifier to mark done")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "ensure":
        inserted = ensure_todo(args.db_path, args.todo_id, args.title)
        if inserted:
            print(f"created: {args.todo_id}")
        else:
            print(f"exists: {args.todo_id}")
        return 0

    if args.command == "complete":
        try:
            complete_todo(args.db_path, args.todo_id)
        except MissingTodoError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"done: {args.todo_id}")
        return 0

    return 2  # unreachable; argparse enforces required subcommand


if __name__ == "__main__":
    sys.exit(main())
