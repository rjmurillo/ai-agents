#!/usr/bin/env python3
"""Tests for skill-doctor session collection."""

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from collect_sessions import (
    discover_hermes_databases,
    find_hermes_sessions,
    parse_hermes_session,
    resolve_hermes_home,
)
from session_common import collect_diagnostics, collection_issue_counts
from session_test_helpers import run_collector


class HermesCollectorTests(unittest.TestCase):
    def _make_db(self, root):
        import sqlite3

        db_path = root / "state.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """CREATE TABLE sessions (
                id TEXT, source TEXT, cwd TEXT, title TEXT, display_name TEXT,
                parent_session_id TEXT, started_at REAL, last_activity_at REAL, ended_at REAL)"""
        )
        conn.execute(
            """CREATE TABLE messages (
                session_id TEXT, role TEXT, content TEXT, tool_calls TEXT, timestamp REAL)"""
        )
        return conn

    def test_parse_hermes_session_extracts_stats_and_skills(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp, closing(self._make_db(Path(tmp))) as conn:
            base = 1_800_000_000.0
            conn.execute(
                "INSERT INTO sessions VALUES ('s1','cli','/tmp/repo','t','d',NULL,?,?,?)",
                (base, base + 60, base + 60),
            )
            conn.execute("INSERT INTO messages VALUES ('s1','user','do the thing',NULL,?)", (base,))
            tool_calls = json.dumps(
                [
                    {"function": {"name": "skill_view", "arguments": '{"name":"my-skill"}'}},
                    {"function": {"name": "terminal", "arguments": "ls"}},
                ]
            )
            conn.execute(
                "INSERT INTO messages VALUES ('s1','assistant','ok',?,?)", (tool_calls, base + 1)
            )
            conn.execute(
                "INSERT INTO messages VALUES ('s1','tool','error: boom',NULL,?)", (base + 2,)
            )
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM sessions").fetchone()

            parsed = parse_hermes_session(conn, row, {"my-skill"}, False)

            self.assertIsNotNone(parsed)
            meta, stats, entries, skills_used = parsed
            self.assertEqual(meta["id"], "s1")
            self.assertEqual(
                meta["started_at"], datetime.fromtimestamp(base, tz=timezone.utc).isoformat()
            )
            self.assertEqual(
                meta["timestamp"], datetime.fromtimestamp(base + 2, tz=timezone.utc).isoformat()
            )
            self.assertEqual(stats["user_turns"], 1)
            self.assertEqual(stats["assistant_turns"], 1)
            self.assertEqual(stats["tool_calls"], 2)
            self.assertEqual(stats["error_outputs"], 1)
            self.assertEqual(
                stats["first_ts"], datetime.fromtimestamp(base, tz=timezone.utc).isoformat()
            )
            self.assertEqual(
                stats["last_ts"], datetime.fromtimestamp(base + 2, tz=timezone.utc).isoformat()
            )
            self.assertEqual(skills_used, ["my-skill"])

    def test_parse_hermes_session_skips_injected_user_content(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp, closing(self._make_db(Path(tmp))) as conn:
            base = 1_800_000_000.0
            conn.execute(
                "INSERT INTO sessions VALUES ('s-inj','cli','/tmp/repo',NULL,NULL,NULL,?,?,?)",
                (base, base + 60, base + 60),
            )
            conn.execute(
                "INSERT INTO messages VALUES "
                "('s-inj','user','<environment_context injected>',NULL,?)",
                (base,),
            )
            conn.execute(
                "INSERT INTO messages VALUES ('s-inj','assistant','ok',?,?)",
                (json.dumps([{"function": {"name": "terminal", "arguments": "ls"}}]), base + 1),
            )
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM sessions WHERE id='s-inj'").fetchone()

            parsed = parse_hermes_session(conn, row, set(), False)

            self.assertIsNotNone(parsed)
            _, stats, entries, _ = parsed
            self.assertEqual(stats["user_turns"], 0)
            self.assertFalse(any(role == "user" for role, _ in entries))

    def test_parse_hermes_session_skips_subagents(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp, closing(self._make_db(Path(tmp))) as conn:
            base = 1_800_000_000.0
            conn.execute(
                "INSERT INTO sessions VALUES ('s2','subagent','/tmp',NULL,NULL,'parent',?,?,?)",
                (base, base, base),
            )
            conn.execute(
                "INSERT INTO messages VALUES ('s2','assistant','hi',?,?)",
                (json.dumps([{"function": {"name": "terminal", "arguments": "ls"}}]), base),
            )
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM sessions").fetchone()

            self.assertIsNone(parse_hermes_session(conn, row, set(), False))
            self.assertIsNotNone(parse_hermes_session(conn, row, set(), True))

    def test_find_hermes_sessions_filters_by_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conn = self._make_db(root)
            old, new = 1_000_000_000.0, datetime.now(tz=timezone.utc).timestamp()
            for sid, started_at, last_activity_at, ended_at in (
                ("old", old, old, old),
                ("recent", new - 30, new - 30, new - 30),
                ("completed", old, None, new),
            ):
                conn.execute(
                    "INSERT INTO sessions VALUES (?,?,?,?,?,NULL,?,?,?)",
                    (sid, "cli", "/tmp", None, None, started_at, last_activity_at, ended_at),
                )
            conn.commit()
            conn.close()

            records, scanned = find_hermes_sessions(
                [root / "state.db"], datetime.fromtimestamp(new - 60, tz=timezone.utc)
            )

            self.assertEqual(scanned, 2)
            self.assertEqual([row["id"] for _, row in records], ["completed", "recent"])

    def test_find_hermes_sessions_skips_incompatible_messages_schema(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "state.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                """CREATE TABLE sessions (
                    id TEXT, source TEXT, cwd TEXT, title TEXT, display_name TEXT,
                    parent_session_id TEXT, started_at REAL,
                    last_activity_at REAL, ended_at REAL)"""
            )
            conn.execute(
                """CREATE TABLE messages (
                    session_id TEXT, role TEXT, content TEXT, timestamp REAL)"""
            )
            ts = datetime.now(tz=timezone.utc).timestamp()
            conn.execute(
                "INSERT INTO sessions VALUES ('bad','cli','/tmp',NULL,NULL,NULL,?,?,?)",
                (ts, ts, ts),
            )
            conn.commit()
            conn.close()

            records, scanned = find_hermes_sessions(
                [db_path], datetime.fromtimestamp(ts - 60, tz=timezone.utc)
            )

            self.assertEqual(records, [])
            self.assertEqual(scanned, 0)

    def test_parse_hermes_session_counts_repeated_calls_by_name_and_args(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp, closing(self._make_db(Path(tmp))) as conn:
            base = 1_800_000_000.0
            conn.execute(
                "INSERT INTO sessions VALUES ('s3','cli','/tmp/repo',NULL,NULL,NULL,?,?,?)",
                (base, base + 60, base + 60),
            )
            tool_calls = json.dumps(
                [
                    {"function": {"name": "terminal", "arguments": "ls"}},
                    {"function": {"name": "terminal", "arguments": "pwd"}},
                    {"function": {"name": "terminal", "arguments": "ls"}},
                ]
            )
            conn.execute(
                "INSERT INTO messages VALUES ('s3','assistant','ok',?,?)", (tool_calls, base + 1)
            )
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM sessions WHERE id='s3'").fetchone()

            parsed = parse_hermes_session(conn, row, set(), False)

            self.assertIsNotNone(parsed)
            _, stats, _, _ = parsed
            self.assertEqual(stats["tool_calls"], 3)
            self.assertEqual(stats["repeated_tool_calls"], 1)

    def test_parse_hermes_session_handles_non_string_tool_args(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp, closing(self._make_db(Path(tmp))) as conn:
            base = 1_800_000_000.0
            conn.execute(
                "INSERT INTO sessions VALUES ('s4','cli','/tmp/repo',NULL,NULL,NULL,?,?,?)",
                (base, base + 60, base + 60),
            )
            tool_calls = json.dumps(
                [
                    {"function": {"name": "skill_view", "arguments": {"name": "my-skill"}}},
                ]
            )
            conn.execute(
                "INSERT INTO messages VALUES ('s4','assistant','ok',?,?)", (tool_calls, base + 1)
            )
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM sessions WHERE id='s4'").fetchone()

            parsed = parse_hermes_session(conn, row, {"my-skill"}, False)

            self.assertIsNotNone(parsed)
            _, stats, entries, skills_used = parsed
            self.assertEqual(stats["tool_calls"], 1)
            self.assertIn(("tool:skill_view", '{"name": "my-skill"}'), entries)
            self.assertEqual(skills_used, ["my-skill"])

    def test_parse_hermes_session_reads_top_level_tool_call_shape(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp, closing(self._make_db(Path(tmp))) as conn:
            base = 1_800_000_000.0
            conn.execute(
                "INSERT INTO sessions VALUES ('s5','cli','/tmp/repo',NULL,NULL,NULL,?,?,?)",
                (base, base + 60, base + 60),
            )
            tool_calls = json.dumps(
                [
                    {"name": "skill_view", "arguments": '{"name":"my-skill"}'},
                ]
            )
            conn.execute(
                "INSERT INTO messages VALUES ('s5','assistant','ok',?,?)", (tool_calls, base + 1)
            )
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM sessions WHERE id='s5'").fetchone()

            parsed = parse_hermes_session(conn, row, {"my-skill"}, False)

            self.assertIsNotNone(parsed)
            _, stats, entries, skills_used = parsed
            self.assertEqual(stats["tool_calls"], 1)
            self.assertIn(("tool:skill_view", '{"name":"my-skill"}'), entries)
            self.assertEqual(skills_used, ["my-skill"])

    def test_discover_hermes_databases_resolves_relative_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hermes_home = root / "hermes-home"
            hermes_home.mkdir()
            (hermes_home / "state.db").write_text("sqlite")

            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                discovered = discover_hermes_databases("hermes-home")
            finally:
                os.chdir(old_cwd)

            self.assertEqual(discovered[0], (hermes_home / "state.db").resolve())

    def test_discover_hermes_databases_explicit_path_is_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env_home = home / "env-hermes"
            env_home.mkdir()
            (env_home / "state.db").write_text("sqlite")
            bad_path = home / "does-not-exist"

            old_home = os.environ.get("HOME")
            old_hermes_home = os.environ.get("HERMES_HOME")
            try:
                os.environ["HOME"] = str(home)
                os.environ["HERMES_HOME"] = str(env_home)
                discovered = discover_hermes_databases(str(bad_path))
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home
                if old_hermes_home is None:
                    os.environ.pop("HERMES_HOME", None)
                else:
                    os.environ["HERMES_HOME"] = old_hermes_home

            self.assertEqual(discovered, [])

    def test_resolve_hermes_home_prefers_dot_hermes_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            dot_hermes = home / ".hermes"
            dot_hermes.mkdir()
            (dot_hermes / "state.db").write_text("sqlite")

            old_home = os.environ.get("HOME")
            old_hermes_home = os.environ.get("HERMES_HOME")
            try:
                os.environ["HOME"] = str(home)
                os.environ.pop("HERMES_HOME", None)
                with patch.object(Path, "home", return_value=home):
                    resolved = resolve_hermes_home(None)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home
                if old_hermes_home is None:
                    os.environ.pop("HERMES_HOME", None)
                else:
                    os.environ["HERMES_HOME"] = old_hermes_home

            self.assertEqual(resolved, dot_hermes.resolve())

    def test_skill_view_malformed_args_preserve_valid_calls(self):
        arguments = [
            "[]",
            "[1]",
            "42",
            "null",
            '"private-transcript"',
            "{",
            '{"name":[]}',
            [],
            [1],
            42,
            False,
            None,
        ]
        with tempfile.TemporaryDirectory() as tmp, closing(self._make_db(Path(tmp))) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("INSERT INTO sessions VALUES ('args','cli','/tmp',NULL,NULL,NULL,1,2,2)")
            calls = [{"function": {"name": "skill_view", "arguments": args}} for args in arguments]
            calls.append({"name": "skill_view", "arguments": '{"name":"my-skill"}'})
            calls.append({"name": "skill_view", "arguments": '{"name":"uninstalled"}'})
            conn.execute(
                "INSERT INTO messages VALUES ('args','assistant','ok',?,2)",
                (json.dumps(calls),),
            )
            row = conn.execute("SELECT * FROM sessions").fetchone()
            with collect_diagnostics():
                parsed = parse_hermes_session(conn, row, {"my-skill"}, False)
                self.assertEqual(collection_issue_counts(), {"malformed_records": len(arguments)})
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed[1]["tool_calls"], len(calls))
            self.assertEqual(parsed[3], ["my-skill"])

    def test_hermes_cli_reports_bad_args_without_losing_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with closing(self._make_db(root)) as conn:
                ts = datetime.now(timezone.utc).timestamp()
                conn.execute(
                    "INSERT INTO sessions VALUES ('args','cli',?,NULL,NULL,NULL,?,?,?)",
                    (str(root), ts, ts, ts),
                )
                calls = [{"name": "skill_view", "arguments": "[42]"}]
                conn.execute(
                    "INSERT INTO messages VALUES ('args','assistant','ok',?,?)",
                    (json.dumps(calls), ts),
                )
                conn.commit()
            result = run_collector(
                root,
                root / "unused",
                "--harness",
                "hermes",
                "--hermes-home",
                str(root),
                "--all-conversations",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            inventory = json.loads((root / "report" / "inventory.json").read_text())
            self.assertEqual(inventory["collection_issues"], {"malformed_records": 1})
            self.assertEqual(inventory["collection_status"], "partial")
            self.assertEqual(inventory["stats"]["sessions_considered"], 1)

    def test_hermes_schema_failures_are_diagnostic(self):
        statements = [
            "DROP TABLE sessions",
            "ALTER TABLE sessions DROP COLUMN cwd",
            "ALTER TABLE sessions DROP COLUMN source",
            "ALTER TABLE messages DROP COLUMN tool_calls",
        ]
        for statement in statements:
            with self.subTest(statement=statement), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                with closing(self._make_db(root)) as conn:
                    conn.execute(statement)
                    conn.commit()
                with collect_diagnostics():
                    found = find_hermes_sessions([root / "state.db"], datetime.now(timezone.utc))
                    self.assertEqual(found, ([], 0))
                    self.assertEqual(collection_issue_counts(), {"schema_failures": 1})

    def test_hermes_database_failure_preserves_next_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with closing(self._make_db(root)) as conn:
                ts = datetime.now(timezone.utc).timestamp()
                conn.execute(
                    "INSERT INTO sessions VALUES ('ok','cli','/tmp',NULL,NULL,NULL,?,?,?)",
                    (ts, ts, ts),
                )
                conn.commit()
            broken = root / "broken.db"
            broken.write_text("not sqlite: private-transcript")
            with collect_diagnostics():
                records, scanned = find_hermes_sessions(
                    [broken, root / "state.db"], datetime.fromtimestamp(ts - 60, timezone.utc)
                )
                self.assertEqual(scanned, 1)
                self.assertEqual(records[0][1]["id"], "ok")
                self.assertEqual(collection_issue_counts(), {"database_failures": 1})

    def test_hermes_message_read_failure_records_issue(self):
        with tempfile.TemporaryDirectory() as tmp, closing(self._make_db(Path(tmp))) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("INSERT INTO sessions VALUES ('read','cli','/tmp',NULL,NULL,NULL,1,2,2)")
            row = conn.execute("SELECT * FROM sessions").fetchone()
            conn.close()
            with collect_diagnostics():
                self.assertIsNone(parse_hermes_session(conn, row, set(), False))
                self.assertEqual(collection_issue_counts(), {"database_failures": 1})

    def test_hermes_os_failure_is_diagnostic(self):
        with patch("session_databases.open_warp_database", side_effect=OSError("unreadable")):
            with collect_diagnostics():
                found = find_hermes_sessions([Path("/unreadable")], datetime.now(timezone.utc))
                self.assertEqual(found, ([], 0))
                self.assertEqual(collection_issue_counts(), {"database_failures": 1})

    def test_hermes_malformed_tool_calls_are_diagnostic(self):
        raw_calls = ["{", "42", "{}", json.dumps([1, {"function": [1]}])]
        for raw in raw_calls:
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as tmp:
                with closing(self._make_db(Path(tmp))) as conn:
                    conn.row_factory = sqlite3.Row
                    conn.execute(
                        "INSERT INTO sessions VALUES ('bad','cli','/tmp',NULL,NULL,NULL,1,2,2)"
                    )
                    conn.execute("INSERT INTO messages VALUES ('bad','assistant','ok',?,2)", (raw,))
                    row = conn.execute("SELECT * FROM sessions").fetchone()
                    with collect_diagnostics():
                        self.assertIsNone(parse_hermes_session(conn, row, set(), False))
                        self.assertEqual(
                            collection_issue_counts(),
                            {"malformed_records": 2 if raw.startswith("[") else 1},
                        )


if __name__ == "__main__":
    unittest.main()
