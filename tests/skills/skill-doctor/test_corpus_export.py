"""Tests for ``--export-corpus`` and the T3 and Gemini corpus adapters."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import session_corpus
import session_corpus_sources
from adr_drift_helpers import symlink_or_skip
from corpus_export_helpers import LONG_TEXT, NOW, OLD, read_rows, run, write_jsonl
from session_common import MAX_MSG_CHARS
from session_corpus import SECRET, CorpusCapture, redact


def claude_record(
    role: str, text: str, ts: str, tool: bool = False, cwd: str = "/work/repo"
) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    if tool:
        blocks.append({"type": "tool_use", "name": "Read", "input": {"file_path": "/x"}})
    return {
        "type": role,
        "timestamp": ts,
        "cwd": cwd,
        "sessionId": "s1",
        "uuid": f"{role}-{ts}",
        "message": {"role": role, "content": blocks},
    }


def make_claude_home(tmp_path: Path, name: str = "claude-home") -> Path:
    home = tmp_path / name
    project = home / "projects" / "-work-repo"
    write_jsonl(
        project / "s1.jsonl",
        [
            claude_record("user", "Please measure the cache.", OLD),
            claude_record("assistant", LONG_TEXT, OLD, tool=True),
            claude_record("assistant", "", OLD),
        ],
    )
    return home


def make_t3_home(
    tmp_path: Path, messages: list[tuple[Any, ...]], columns: str | None = None
) -> Path:
    home = tmp_path / "t3-home"
    db = home / "userdata" / "statev2.sqlite"
    db.parent.mkdir(parents=True)
    connection = sqlite3.connect(db)
    connection.execute(
        "CREATE TABLE orchestration_v2_projection_threads (thread_id TEXT, title TEXT)"
    )
    connection.execute(
        "INSERT INTO orchestration_v2_projection_threads VALUES ('t1', 'Cache work')"
    )
    cols = (
        columns or "message_id TEXT, thread_id TEXT, role TEXT, created_at TEXT, payload_json TEXT"
    )
    connection.execute(f"CREATE TABLE orchestration_v2_projection_messages ({cols})")
    if columns is None:
        connection.executemany(
            "INSERT INTO orchestration_v2_projection_messages VALUES (?, ?, ?, ?, ?)", messages
        )
    connection.commit()
    connection.close()
    return home


def make_gemini_home(tmp_path: Path, records: list[dict[str, Any]]) -> Path:
    home = tmp_path / "gemini-home"
    log = home / "brain" / "abc123" / ".system_generated" / "logs" / "transcript_full.jsonl"
    write_jsonl(log, records)
    return home


def export_args(tmp_path: Path, home: Path, out_name: str = "corpus.jsonl") -> list[str]:
    return [
        "--claude-home", str(home),
        "--out", str(tmp_path / "report"),
        "--export-corpus", str(tmp_path / out_name),
    ]  # fmt: skip


# ---- Claude export: row shape, no truncation, scope ----


def test_export_writes_documented_row_shape(tmp_path: Path) -> None:
    home = make_claude_home(tmp_path)
    result = run(tmp_path, *export_args(tmp_path, home), "--all-conversations")
    assert result.returncode == 0, result.stderr
    rows = read_rows(tmp_path / "corpus.jsonl")
    assert {tuple(sorted(r)) for r in rows} == {
        ("line", "path", "role", "session", "source", "text", "ts")
    }
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert {r["source"] for r in rows} == {"claude"}
    assert {r["session"] for r in rows} == {"s1"}
    assert [r["line"] for r in rows] == [1, 2]  # physical line, empty record on line 3 skipped
    assert rows[0]["ts"] == OLD


def test_export_keeps_full_text_where_transcripts_truncate(tmp_path: Path) -> None:
    home = make_claude_home(tmp_path)
    run(tmp_path, *export_args(tmp_path, home), "--all-conversations")
    rows = read_rows(tmp_path / "corpus.jsonl")
    assert rows[1]["text"] == LONG_TEXT
    assert len(LONG_TEXT) > MAX_MSG_CHARS
    transcripts = list((tmp_path / "report" / "transcripts").glob("*.md"))
    assert transcripts and "truncated" in transcripts[0].read_text(encoding="utf-8")


def test_export_has_no_head_tail_cap_on_long_sessions(tmp_path: Path) -> None:
    home = tmp_path / "claude-home"
    records = [
        claude_record("user" if i % 2 == 0 else "assistant", f"message {i}", OLD, tool=i == 1)
        for i in range(400)
    ]
    write_jsonl(home / "projects" / "-work-repo" / "s1.jsonl", records)
    run(tmp_path, *export_args(tmp_path, home), "--all-conversations")
    assert len(read_rows(tmp_path / "corpus.jsonl")) == 400


def test_session_without_tool_calls_is_still_exported(tmp_path: Path) -> None:
    home = tmp_path / "claude-home"
    write_jsonl(
        home / "projects" / "-work-repo" / "s1.jsonl",
        [claude_record("user", "talk only", OLD), claude_record("assistant", "answer", OLD)],
    )
    run(tmp_path, *export_args(tmp_path, home), "--all-conversations")
    assert len(read_rows(tmp_path / "corpus.jsonl")) == 2


def test_repo_scope_admits_a_matching_session_and_drops_another(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "claude-home"
    write_jsonl(
        home / "projects" / "-repo" / "s1.jsonl",
        [claude_record("user", "in scope", OLD, tool=True, cwd=str(repo))],
    )
    run(tmp_path, *export_args(tmp_path, home), "--repo", str(repo))
    assert [r["text"] for r in read_rows(tmp_path / "corpus.jsonl")] == ["in scope"]
    other = tmp_path / "another-repo"
    other.mkdir()
    run(tmp_path, *export_args(tmp_path, home, "corpus2.jsonl"), "--repo", str(other))
    assert (tmp_path / "corpus2.jsonl").read_text(encoding="utf-8") == ""


def test_session_outside_time_window_is_not_exported(tmp_path: Path) -> None:
    home = make_claude_home(tmp_path)
    old = NOW - timedelta(days=90)
    for path in home.rglob("*.jsonl"):
        os.utime(path, (old.timestamp(), old.timestamp()))
    run(tmp_path, *export_args(tmp_path, home), "--all-conversations")
    assert (tmp_path / "corpus.jsonl").read_text(encoding="utf-8") == ""


# ---- default output is unchanged without the flag ----


def snapshot(report: Path) -> dict[str, str]:
    inventory = json.loads((report / "inventory.json").read_text(encoding="utf-8"))
    inventory.pop("generated_at")
    inventory = json.loads(json.dumps(inventory).replace(str(report), "<out>"))
    files = {p.name: p.read_text(encoding="utf-8") for p in (report / "transcripts").glob("*.md")}
    return {"inventory": json.dumps(inventory, sort_keys=True), **files}


def test_default_output_is_identical_with_and_without_the_flag(tmp_path: Path) -> None:
    home = make_claude_home(tmp_path)
    common = ["--claude-home", str(home), "--all-conversations"]
    run(tmp_path, *common, "--out", str(tmp_path / "plain"))
    run(
        tmp_path,
        *common,
        "--out",
        str(tmp_path / "exported"),
        "--export-corpus",
        str(tmp_path / "c.jsonl"),
    )
    assert snapshot(tmp_path / "plain") == snapshot(tmp_path / "exported")
    assert not (tmp_path / "plain" / "c.jsonl").exists()


def test_flag_absent_reads_no_t3_or_gemini_source(tmp_path: Path) -> None:
    home = make_claude_home(tmp_path)
    t3 = make_t3_home(tmp_path, [("m1", "t1", "user", OLD, json.dumps({"text": "hi"}))])
    result = run(
        tmp_path, "--claude-home", str(home), "--t3-home", str(t3), "--all-conversations",
        "--out", str(tmp_path / "report"),
    )  # fmt: skip
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    assert result.returncode == 0
    assert "t3" not in inventory["sources"]


# ---- redaction ----


def test_redact_replaces_every_token_shape() -> None:
    secrets = [
        "sk-" + "a" * 24,
        "ghp_" + "b" * 36,
        "github_pat_" + "c" * 30,
        "AKIA" + "D" * 16,
        "eyJ" + "e" * 24 + "." + "f" * 12,
        "xoxb-" + "1" * 12,
        "Bearer " + "g" * 30,
    ]
    for secret in secrets:
        assert redact(f"key {secret} end") == "key [REDACTED] end"


def test_redact_leaves_ordinary_text_alone() -> None:
    text = "the sk-short token and Bearer x are not secrets, 12 ms vs 9 ms"
    assert redact(text) == text
    assert not SECRET.search(text)


def test_exported_text_is_redacted(tmp_path: Path) -> None:
    token = "ghp_" + "z" * 36
    home = tmp_path / "claude-home"
    write_jsonl(
        home / "projects" / "-work-repo" / "s1.jsonl",
        [claude_record("user", f"use {token} now", OLD, tool=True)],
    )
    run(tmp_path, *export_args(tmp_path, home), "--all-conversations")
    exported = (tmp_path / "corpus.jsonl").read_text(encoding="utf-8")
    assert token not in exported
    assert "use [REDACTED] now" in exported


# ---- output path guard ----


@pytest.mark.parametrize("spelling", ["direct", "symlink"])
def test_export_refuses_to_write_inside_the_skill_directory(tmp_path: Path, spelling: str) -> None:
    home = make_claude_home(tmp_path)
    skill_dir = session_corpus.SKILL_ROOT
    if spelling == "symlink":
        link = tmp_path / "alias"
        symlink_or_skip(link, skill_dir)
        target = link / "corpus.jsonl"
    else:
        target = skill_dir / "corpus.jsonl"
    result = run(
        tmp_path, "--claude-home", str(home), "--out", str(tmp_path / "report"),
        "--export-corpus", str(target),
    )  # fmt: skip
    assert result.returncode == 2
    assert "skill directory" in result.stderr
    assert not (skill_dir / "corpus.jsonl").exists()


def test_export_refuses_a_directory_path(tmp_path: Path) -> None:
    home = make_claude_home(tmp_path)
    result = run(
        tmp_path, "--claude-home", str(home), "--out", str(tmp_path / "report"),
        "--export-corpus", str(tmp_path),
    )  # fmt: skip
    assert result.returncode == 2
    assert "directory" in result.stderr


def test_export_refuses_to_overwrite_a_file(tmp_path: Path) -> None:
    home = make_claude_home(tmp_path)
    target = tmp_path / "corpus.jsonl"
    target.write_text("keep this", encoding="utf-8")
    result = run(tmp_path, *export_args(tmp_path, home))
    assert result.returncode == 2
    assert "refuses to overwrite" in result.stderr
    assert target.read_text(encoding="utf-8") == "keep this"


def test_corpus_only_harness_needs_the_flag(tmp_path: Path) -> None:
    result = run(tmp_path, "--harness", "t3", "--out", str(tmp_path / "report"))
    assert result.returncode == 2
    assert "--export-corpus" in result.stderr


# ---- T3 adapter ----


def t3_row(mid: str, role: str, payload: object, ts: str = OLD) -> tuple[Any, ...]:
    return (mid, "t1", role, ts, json.dumps(payload))


def test_t3_rows_export_with_message_id_as_line(tmp_path: Path) -> None:
    t3 = make_t3_home(
        tmp_path,
        [
            t3_row("m1", "user", {"text": "why slow"}),
            t3_row("m2", "assistant", {"content": "12 ms"}),
        ],
    )
    result = run(
        tmp_path, "--harness", "t3", "--all-conversations", "--t3-home", str(t3),
        "--out", str(tmp_path / "report"), "--export-corpus", str(tmp_path / "c.jsonl"),
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    rows = read_rows(tmp_path / "c.jsonl")
    assert [(r["source"], r["session"], r["line"], r["role"], r["text"]) for r in rows] == [
        ("t3", "t1", "m1", "user", "why slow"),
        ("t3", "t1", "m2", "assistant", "12 ms"),
    ]
    assert rows[0]["path"] == "t3:t1"


def test_t3_list_of_blocks_content_is_joined(tmp_path: Path) -> None:
    blocks = [
        {"type": "text", "text": "first"},
        {"type": "image"},
        {"type": "text", "text": "second"},
    ]
    t3 = make_t3_home(tmp_path, [t3_row("m1", "assistant", {"content": blocks})])
    run(
        tmp_path, "--harness", "t3", "--all-conversations", "--t3-home", str(t3),
        "--out", str(tmp_path / "report"), "--export-corpus", str(tmp_path / "c.jsonl"),
    )  # fmt: skip
    assert read_rows(tmp_path / "c.jsonl")[0]["text"] == "first\nsecond"


def test_t3_skips_other_roles_malformed_payloads_and_old_messages(tmp_path: Path) -> None:
    stale = (NOW - timedelta(days=90)).isoformat()
    connection_rows = [
        t3_row("m1", "system", {"text": "ignore"}),
        ("m2", "t1", "user", OLD, "{not json"),
        t3_row("m3", "assistant", {"text": "stale"}, ts=stale),
        t3_row("m4", "assistant", {"text": "kept"}),
    ]
    t3 = make_t3_home(tmp_path, connection_rows)
    result = run(
        tmp_path, "--harness", "t3", "--all-conversations", "--t3-home", str(t3),
        "--out", str(tmp_path / "report"), "--export-corpus", str(tmp_path / "c.jsonl"),
    )  # fmt: skip
    assert [r["text"] for r in read_rows(tmp_path / "c.jsonl")] == ["kept"]
    assert "malformed_records" in result.stderr


def test_t3_schema_mismatch_is_a_collection_issue_not_a_crash(tmp_path: Path) -> None:
    t3 = make_t3_home(tmp_path, [], columns="message_id TEXT, thread_id TEXT")
    result = run(
        tmp_path, "--harness", "t3", "--all-conversations", "--t3-home", str(t3),
        "--out", str(tmp_path / "report"), "--export-corpus", str(tmp_path / "c.jsonl"),
    )  # fmt: skip
    assert "Traceback" not in result.stderr
    assert "schema_mismatch" in result.stderr
    assert (tmp_path / "c.jsonl").read_text(encoding="utf-8") == ""


def test_t3_database_is_opened_read_only(tmp_path: Path) -> None:
    t3 = make_t3_home(tmp_path, [])
    connection = session_corpus_sources.open_t3_database(session_corpus_sources.t3_database(t3))
    with pytest.raises(sqlite3.OperationalError):
        connection.execute("DELETE FROM orchestration_v2_projection_threads")
    connection.close()


def test_unreadable_t3_database_is_a_collection_issue(tmp_path: Path) -> None:
    home = tmp_path / "t3-home"
    db = home / "userdata" / "statev2.sqlite"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"not a database" * 50)
    result = run(
        tmp_path, "--harness", "t3", "--all-conversations", "--t3-home", str(home),
        "--out", str(tmp_path / "report"), "--export-corpus", str(tmp_path / "c.jsonl"),
    )  # fmt: skip
    assert "Traceback" not in result.stderr
    assert "database_failures" in result.stderr


# ---- Gemini adapter ----


def test_gemini_reads_planner_and_user_records_only(tmp_path: Path) -> None:
    gemini = make_gemini_home(
        tmp_path,
        [
            {"type": "USER_INPUT", "content": "question", "timestamp": OLD},
            {"type": "PLANNER_RESPONSE", "content": "answer 5 vs 3", "timestamp": OLD},
            {"type": "TOOL_CALL", "content": "ignored", "timestamp": OLD},
            {"type": "PLANNER_RESPONSE", "content": ["not", "a", "string"]},
        ],
    )
    result = run(
        tmp_path, "--harness", "gemini", "--all-conversations", "--gemini-home", str(gemini),
        "--out", str(tmp_path / "report"), "--export-corpus", str(tmp_path / "c.jsonl"),
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    rows = read_rows(tmp_path / "c.jsonl")
    assert [(r["source"], r["session"], r["role"], r["text"]) for r in rows] == [
        ("gemini", "abc123", "user", "question"),
        ("gemini", "abc123", "assistant", "answer 5 vs 3"),
    ]


# ---- missing sources are skipped ----


def test_missing_t3_and_gemini_sources_are_skipped_under_auto(tmp_path: Path) -> None:
    home = make_claude_home(tmp_path)
    result = run(
        tmp_path, *export_args(tmp_path, home), "--all-conversations",
        "--t3-home", str(tmp_path / "none"), "--gemini-home", str(tmp_path / "none"),
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    assert len(read_rows(tmp_path / "corpus.jsonl")) == 2


def test_naming_a_missing_corpus_source_is_an_error(tmp_path: Path) -> None:
    result = run(
        tmp_path, "--harness", "gemini", "--gemini-home", str(tmp_path / "none"),
        "--all-conversations", "--out", str(tmp_path / "report"),
        "--export-corpus", str(tmp_path / "c.jsonl"),
    )  # fmt: skip
    assert result.returncode == 2
    assert "gemini source not found" in result.stderr
    assert not (tmp_path / "c.jsonl").exists()


def test_t3_and_gemini_are_out_of_scope_without_all_conversations(tmp_path: Path) -> None:
    t3 = make_t3_home(tmp_path, [t3_row("m1", "user", {"text": "hello"})])
    result = run(
        tmp_path, "--harness", "t3", "--t3-home", str(t3), "--repo", str(tmp_path),
        "--out", str(tmp_path / "report"), "--export-corpus", str(tmp_path / "c.jsonl"),
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "c.jsonl").read_text(encoding="utf-8") == ""


# ---- capture unit behavior ----


def test_capture_ignores_non_conversation_roles_and_blank_text() -> None:
    capture = CorpusCapture()
    capture.begin()
    capture.record("tool:Read", "x", None)
    capture.record("child-agent", "x", None)
    capture.record("user", "   ", None)
    capture.record("user", "kept", "ts")
    assert [r["text"] for r in capture.rows] == ["kept"]
    assert capture.rows[0]["line"] == 1


def test_capture_begin_discards_the_previous_session() -> None:
    capture = CorpusCapture()
    capture.record("user", "old", None)
    capture.begin()
    assert capture.rows == []
