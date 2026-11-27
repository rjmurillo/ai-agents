"""Regression tests for the corpus export review fixes."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import session_corpus
import session_corpus_sources
from corpus_export_helpers import NOW, read_rows, run
from session_corpus import CorpusCapture, redact
from test_corpus_export import make_t3_home


@pytest.mark.parametrize(
    "secret",
    [
        "gho_" + "h" * 36,
        "ghu_" + "h" * 36,
        "ghs_" + "h" * 36,
        "ghr_" + "h" * 36,
        "bearer " + "i" * 30,
        "Authorization: token " + "j" * 30,
    ],
)
def test_redact_covers_more_github_and_header_shapes(secret: str) -> None:
    assert redact(f"key {secret} end") == "key [REDACTED] end"


def test_redact_keeps_sk_inside_a_hyphenated_word() -> None:
    text = "see the risk-assessment-for-the-cache-layer doc"
    assert redact(text) == text


def test_t3_reader_sees_rows_a_live_wal_writer_commits(tmp_path: Path) -> None:
    t3 = make_t3_home(tmp_path, [])
    path = session_corpus_sources.t3_database(t3)
    writer = sqlite3.connect(path)
    writer.execute("PRAGMA journal_mode=WAL")
    reader = session_corpus_sources.open_t3_database(path)
    count = "SELECT COUNT(*) FROM orchestration_v2_projection_threads"
    assert reader.execute(count).fetchone()[0] == 1
    writer.execute("INSERT INTO orchestration_v2_projection_threads VALUES ('t2', 'New')")
    writer.commit()
    assert reader.execute(count).fetchone()[0] == 2
    reader.close()
    writer.close()


def test_failed_export_removes_its_partial_file(tmp_path: Path) -> None:
    target = tmp_path / "c.jsonl"
    args = argparse.Namespace(export_corpus=str(target), harness="auto")
    with pytest.raises(RuntimeError), session_corpus.corpus_export(args) as exporter:
        assert exporter is not None
        exporter._stream.write("partial\n")
        raise RuntimeError("boom")
    assert not target.exists()
    assert session_corpus.current_capture() is None


def test_capture_converts_datetime_timestamps_to_iso_strings() -> None:
    capture = CorpusCapture()
    stamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    capture.record("user", "hello", stamp)
    assert capture.rows[0]["ts"] == "2026-01-02T03:04:05+00:00"


def make_hermes_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    started = (NOW - timedelta(hours=3)).timestamp()
    connection = sqlite3.connect(path)
    connection.execute(
        """CREATE TABLE sessions (
            id TEXT, source TEXT, cwd TEXT, title TEXT, display_name TEXT,
            parent_session_id TEXT, started_at REAL, last_activity_at REAL, ended_at REAL)"""
    )
    connection.execute(
        """CREATE TABLE messages (
            session_id TEXT, role TEXT, content TEXT, tool_calls TEXT, timestamp REAL)"""
    )
    connection.execute(
        "INSERT INTO sessions VALUES ('h1', 'cli', '/work/repo', 'chat', NULL, NULL, ?, ?, ?)",
        (started, started + 60, started + 60),
    )
    connection.executemany(
        "INSERT INTO messages VALUES ('h1', ?, ?, NULL, ?)",
        [("user", "why slow", started + 1), ("assistant", "12 ms vs 9 ms", started + 2)],
    )
    connection.commit()
    connection.close()


def test_hermes_chat_only_session_exports_with_iso_timestamps(tmp_path: Path) -> None:
    make_hermes_db(tmp_path / "isolated-home" / "hermes_home" / "state.db")
    result = run(
        tmp_path, "--harness", "hermes", "--all-conversations",
        "--out", str(tmp_path / "report"), "--export-corpus", str(tmp_path / "c.jsonl"),
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    rows = read_rows(tmp_path / "c.jsonl")
    assert [(r["source"], r["role"], r["text"], r["line"]) for r in rows] == [
        ("hermes", "user", "why slow", 1),
        ("hermes", "assistant", "12 ms vs 9 ms", 2),
    ]
    for exported in rows:
        assert isinstance(exported["ts"], str)
        datetime.fromisoformat(exported["ts"])
