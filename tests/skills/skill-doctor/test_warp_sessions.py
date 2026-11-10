"""Synthetic SQLite and wire-format coverage for the Warp collector."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import pytest
import session_databases as databases
from session_common import collect_diagnostics, collection_issue_counts
from session_test_helpers import run_collector
from warp_decoder import decode_task


def varint(value):
    encoded = bytearray()
    while value > 127:
        encoded.append((value & 127) | 128)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def field(number, payload):
    if isinstance(payload, str):
        payload = payload.encode()
    return varint((number << 3) | 2) + varint(len(payload)) + payload


def task_blob(text="working"):
    """Encode the subset read by warp_decoder.decode_task and _decode_message."""
    user = field(2, field(1, "please inspect"))
    assistant = field(3, field(1, text))
    skill = field(26, field(1, "/skills/my-skill/SKILL.md") + field(3, "my-skill"))
    call = field(4, field(1, "call-id") + skill)
    return field(1, "task-id") + b"".join(field(5, msg) for msg in (user, assistant, call))


def make_database(tmp_path, channel="stable"):
    path = tmp_path / channel / "warp.sqlite"
    path.parent.mkdir(parents=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """CREATE TABLE agent_conversations (
                conversation_id TEXT, conversation_data TEXT,
                last_modified_at TEXT, summary TEXT);
            CREATE TABLE agent_tasks (id INTEGER, conversation_id TEXT, task BLOB);
            CREATE TABLE ai_queries (
                conversation_id TEXT, start_ts TEXT, working_directory TEXT);"""
        )
    return path


def add_conversation(path, sid="healthy", *, metadata="{}", summary="{}", blob=None, age=0):
    now = datetime.now(timezone.utc) - timedelta(seconds=age)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "INSERT INTO agent_conversations VALUES (?, ?, ?, ?)",
            (sid, metadata, timestamp, summary),
        )
        connection.execute(
            "INSERT INTO agent_tasks VALUES (1, ?, ?)",
            (sid, task_blob() if blob is None else blob),
        )
        connection.execute(
            "INSERT INTO ai_queries VALUES (?, ?, ?)", (sid, timestamp, str(path.parent))
        )
        connection.commit()


def run_warp(tmp_path, *paths, extra=()):
    args = [arg for path in paths for arg in ("--warp-db", str(path))]
    result = run_collector(
        tmp_path, tmp_path / "unused", "--harness", "warp", "--all-conversations", *args, *extra
    )
    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text())
    return result, inventory


def records(path):
    return databases.find_warp_conversations(
        [path], datetime.now(timezone.utc) - timedelta(days=1)
    )[0]


def test_wire_fixture_decodes_real_envelope():
    decoded = decode_task(task_blob())
    assert decoded["id"] == "task-id"
    assert [message["kind"] for message in decoded["messages"]] == [
        "user_query",
        "agent_output",
        "tool_call",
    ]
    assert decoded["messages"][2]["name"] == "read_skill"
    assert decoded["messages"][2]["skill"]["name"] == "my-skill"


def test_warp_cli_collects_valid_session_and_transcript(tmp_path):
    path = make_database(tmp_path)
    add_conversation(path)
    result, inventory = run_warp(tmp_path, path)
    assert inventory["collection_issues"] == {}
    assert inventory["collection_status"] == "complete"
    assert inventory["stats"]["sessions_considered"] == 1
    session = inventory["sessions"][0]
    assert session["meta"]["id"] == "healthy"
    assert session["meta"]["cwd"] == str(path.parent)
    assert session["stats"]["tool_calls"] == 1
    assert session["stats"]["assistant_turns"] == 1
    transcript = (tmp_path / "report" / "transcripts" / "warp-healthy.md").read_text()
    assert "working" in transcript
    assert "read_skill" in transcript
    assert result.stderr == ""


@pytest.mark.parametrize("parent_key", ["parent_agent_id", "parent_conversation_id"])
@pytest.mark.parametrize("include", [False, True])
def test_warp_cli_child_exclusion_is_not_failure(tmp_path, parent_key, include):
    path = make_database(tmp_path)
    add_conversation(path, metadata=json.dumps({parent_key: "parent"}))
    extra = ("--include-subagents",) if include else ()
    _, inventory = run_warp(tmp_path, path, extra=extra)
    assert inventory["collection_issues"] == {}
    assert inventory["stats"]["sessions_considered"] == int(include)
    if include:
        assert inventory["sessions"][0]["meta"]["thread_source"] == "subagent"


def test_warp_cli_deduplicates_channels_using_newest_snapshot(tmp_path):
    stable = make_database(tmp_path)
    preview = make_database(tmp_path, "preview")
    add_conversation(stable, blob=task_blob("old snapshot"), age=60)
    add_conversation(preview, blob=task_blob("new snapshot"))
    _, inventory = run_warp(tmp_path, stable, preview)
    source = inventory["sources"]["warp"]
    assert source["records_in_window"] == 2
    assert source["records_after_channel_deduplication"] == 1
    assert inventory["stats"]["sessions_considered"] == 1
    assert inventory["sessions"][0]["meta"]["channel"] == "preview"
    transcript = (tmp_path / "report" / "transcripts" / "warp-healthy.md").read_text()
    assert "new snapshot" in transcript
    assert "old snapshot" not in transcript


@pytest.mark.parametrize("column", ["metadata", "summary"])
@pytest.mark.parametrize(
    "value", ['["private-transcript"]', "42", "null", '"private-transcript"', "false", "{"]
)
def test_warp_cli_skips_bad_metadata_preserving_healthy(tmp_path, column, value):
    path = make_database(tmp_path)
    add_conversation(path)
    add_conversation(path, "bad", **{column: value})
    result, inventory = run_warp(tmp_path, path)
    assert [session["meta"]["id"] for session in inventory["sessions"]] == ["healthy"]
    assert inventory["collection_issues"] == {"malformed_records": 1}
    assert inventory["collection_status"] == "partial"
    assert "malformed_records=1" in result.stderr
    assert "private-transcript" not in result.stderr


@pytest.mark.parametrize("blob", [b"\x80", b"\x00", b"\x2a\x7fshort", "not-a-blob"])
def test_warp_cli_skips_bad_protobuf_preserving_healthy(tmp_path, blob):
    path = make_database(tmp_path)
    add_conversation(path)
    add_conversation(path, "bad", blob=blob)
    result, inventory = run_warp(tmp_path, path)
    assert inventory["collection_issues"] == {"decode_failures": 1}
    assert [session["meta"]["id"] for session in inventory["sessions"]] == ["healthy"]
    assert "not-a-blob" not in result.stderr


@pytest.mark.parametrize(
    "statement",
    [
        "DROP TABLE agent_tasks",
        "ALTER TABLE agent_tasks RENAME COLUMN task TO unknown",
        "ALTER TABLE agent_conversations RENAME COLUMN conversation_data TO unknown",
        "ALTER TABLE ai_queries RENAME COLUMN start_ts TO unknown",
    ],
)
def test_warp_cli_reports_incompatible_schema(tmp_path, statement):
    healthy = make_database(tmp_path)
    broken = make_database(tmp_path, "broken")
    add_conversation(healthy)
    add_conversation(broken, "bad")
    with closing(sqlite3.connect(broken)) as connection:
        connection.execute(statement)
        connection.commit()
    _, inventory = run_warp(tmp_path, healthy, broken)
    assert inventory["collection_issues"] == {"schema_failures": 1}
    assert [session["meta"]["id"] for session in inventory["sessions"]] == ["healthy"]


@pytest.mark.parametrize(
    "failure", [OSError("private-transcript"), sqlite3.OperationalError("locked")]
)
def test_warp_read_failure_records_issue_and_next_database_survives(tmp_path, monkeypatch, failure):
    path = make_database(tmp_path)
    add_conversation(path)
    original = databases.open_warp_database

    def open_database(candidate):
        if candidate.name == "broken.sqlite":
            raise failure
        return original(candidate)

    monkeypatch.setattr(databases, "open_warp_database", open_database)
    with collect_diagnostics():
        found, scanned = databases.find_warp_conversations(
            [tmp_path / "broken.sqlite", path],
            datetime.now(timezone.utc) - timedelta(days=1),
        )
        assert len(found) == scanned == 1
        assert collection_issue_counts() == {"database_failures": 1}


def test_warp_snapshot_read_failure_is_diagnostic(tmp_path):
    path = make_database(tmp_path)
    add_conversation(path)
    record = records(path)[0]
    path.unlink()
    with collect_diagnostics():
        assert databases.parse_warp_conversation(record, set(), False) is None
        assert collection_issue_counts() == {"database_failures": 1}


def test_warp_snapshot_size_boundary(tmp_path, monkeypatch):
    path = make_database(tmp_path)
    blob = task_blob()
    add_conversation(path, blob=blob)
    monkeypatch.setattr(databases, "MAX_WARP_CONVERSATION_BYTES", len(blob) - 1)
    with collect_diagnostics():
        assert databases.parse_warp_conversation(records(path)[0], set(), False) is None
        assert collection_issue_counts() == {"decode_failures": 1}
    monkeypatch.setattr(databases, "MAX_WARP_CONVERSATION_BYTES", len(blob))
    with collect_diagnostics():
        assert databases.parse_warp_conversation(records(path)[0], set(), False) is not None
        assert collection_issue_counts() == {}


@pytest.mark.parametrize("column", ["metadata", "summary"])
@pytest.mark.parametrize("value", [None, "", "{}"])
def test_warp_optional_metadata_is_not_malformed(tmp_path, column, value):
    path = make_database(tmp_path)
    add_conversation(path, **{column: value})
    with collect_diagnostics():
        assert databases.parse_warp_conversation(records(path)[0], {"my-skill"}, False) is not None
        assert collection_issue_counts() == {}


def test_warp_cli_uses_explicit_skill_reference(tmp_path):
    path = make_database(tmp_path)
    add_conversation(path)
    skill_dir = tmp_path / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: my-skill\n---\nSynthetic skill.\n")
    _, inventory = run_warp(tmp_path, path, extra=("--skills-dir", str(skill_dir.parent)))
    assert inventory["sessions"][0]["skills_used"] == ["my-skill"]
    assert inventory["skill_usage"]["my-skill"] == 1


def test_warp_optional_query_table_and_summary_column(tmp_path):
    path = make_database(tmp_path)
    add_conversation(path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("DROP TABLE ai_queries")
        connection.execute("ALTER TABLE agent_conversations DROP COLUMN summary")
        connection.commit()
    with collect_diagnostics():
        assert databases.parse_warp_conversation(records(path)[0], set(), False) is not None
        assert collection_issue_counts() == {}


def test_warp_query_table_without_working_directory_reads_start_time(tmp_path):
    path = make_database(tmp_path)
    add_conversation(path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("ALTER TABLE ai_queries DROP COLUMN working_directory")
        connection.commit()

    blobs, first_query_at, working_directory = databases.load_warp_conversation_data(
        records(path)[0]
    )

    assert len(blobs) == 1
    assert first_query_at is not None
    assert working_directory is None


def test_warp_query_table_with_working_directory_reads_it(tmp_path):
    path = make_database(tmp_path)
    add_conversation(path)

    _, _, working_directory = databases.load_warp_conversation_data(records(path)[0])

    assert working_directory == str(path.parent)


def test_warp_corrupt_database_preserves_healthy_records(tmp_path):
    path = make_database(tmp_path)
    add_conversation(path)
    corrupt = tmp_path / "corrupt.sqlite"
    corrupt.write_bytes(b"not sqlite: private-transcript")
    with collect_diagnostics():
        found, scanned = databases.find_warp_conversations(
            [corrupt, path], datetime.now(timezone.utc) - timedelta(days=1)
        )
        assert len(found) == scanned == 1
        assert collection_issue_counts() == {"database_failures": 1}
    result, inventory = run_warp(tmp_path, corrupt, path)
    assert inventory["collection_issues"] == {"database_failures": 1}
    assert [session["meta"]["id"] for session in inventory["sessions"]] == ["healthy"]
    assert "private-transcript" not in result.stderr


def test_warp_missing_conversation_table_is_schema_failure(tmp_path):
    path = make_database(tmp_path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("DROP TABLE agent_conversations")
        connection.commit()
    with collect_diagnostics():
        assert records(path) == []
        assert collection_issue_counts() == {"schema_failures": 1}


def test_warp_cli_rejects_oversized_aggregate_snapshot(tmp_path):
    path = make_database(tmp_path)
    add_conversation(path)
    add_conversation(path, "oversized")
    half_size = databases.MAX_WARP_CONVERSATION_BYTES // 2 + 1
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "UPDATE agent_tasks SET task = zeroblob(?) WHERE conversation_id = 'oversized'",
            (half_size,),
        )
        connection.execute(
            "INSERT INTO agent_tasks VALUES (2, 'oversized', zeroblob(?))", (half_size,)
        )
        connection.commit()
    record = next(record for record in records(path) if record["conversation_id"] == "oversized")
    with pytest.raises(databases.ProtobufDecodeError, match="snapshot.*limit"):
        databases.load_warp_conversation_data(record)
    _, inventory = run_warp(tmp_path, path)
    assert inventory["collection_issues"] == {"decode_failures": 1}
    assert [session["meta"]["id"] for session in inventory["sessions"]] == ["healthy"]


def test_warp_message_order_skill_invocation_and_tool_results(tmp_path):
    path = make_database(tmp_path)
    descriptor = field(1, "/skills/my-skill/SKILL.md") + field(2, "my-skill")
    invoke = field(23, field(1, field(1, descriptor)) + field(2, field(1, "invoke")))
    edit = field(4, field(1, "edit-id") + field(6, field(1, "patch")))
    context = field(1, field(1, str(tmp_path)))
    result = field(5, field(6, field(1, "error: rejected")) + field(11, context))
    assistant = field(3, field(1, "done"))
    messages = [invoke, edit, result, assistant]
    timestamped = [
        message + field(14, varint(8) + varint(1_800_000_000 + index))
        for index, message in enumerate(messages)
    ]
    blob = field(1, "ordered") + b"".join(field(5, msg) for msg in reversed(timestamped))
    add_conversation(path, blob=blob)
    with collect_diagnostics():
        parsed = databases.parse_warp_conversation(records(path)[0], {"my-skill"}, False)
        assert collection_issue_counts() == {}
    meta, stats, entries, skills = parsed
    assert skills == ["my-skill"]
    assert meta["started_at"] == datetime.fromtimestamp(1_800_000_000, timezone.utc).isoformat()
    assert stats["has_code_edits"] is True
    assert stats["error_outputs"] == 1
    assert [role for role, _ in entries] == [
        "skill",
        "user",
        "tool:apply_file_diffs",
        "output",
        "assistant",
    ]
