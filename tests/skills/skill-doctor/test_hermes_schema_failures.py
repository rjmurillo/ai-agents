"""Hermes rows with non-text content fail one session, not the whole run."""

import sqlite3
from contextlib import closing

from collect_sessions import parse_hermes_session
from session_common import collect_diagnostics, collection_issue_counts


def _database(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """CREATE TABLE sessions (
            id TEXT, source TEXT, cwd TEXT, title TEXT, display_name TEXT,
            parent_session_id TEXT, started_at REAL, last_activity_at REAL, ended_at REAL);
        CREATE TABLE messages (
            session_id TEXT, role TEXT, content TEXT, tool_calls TEXT, timestamp REAL);"""
    )
    return connection


def test_non_text_content_is_a_schema_failure_for_that_session(tmp_path):
    base = 1_800_000_000.0
    with closing(_database(tmp_path / "state.db")) as connection:
        connection.execute(
            "INSERT INTO sessions VALUES ('s1','cli','/tmp/repo','t','d',NULL,?,?,?)",
            (base, base + 60, base + 60),
        )
        connection.execute(
            "INSERT INTO messages VALUES ('s1','user',?,NULL,?)", (b"\x00binary", base)
        )
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM sessions").fetchone()

        with collect_diagnostics():
            parsed = parse_hermes_session(connection, row, {"my-skill"}, False)
            issues = collection_issue_counts()

    assert parsed is None
    assert issues == {"schema_failures": 1}
