"""Corpus export regressions from the PR 7870 review: lines, event-only Codex, paths, redaction."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import session_corpus
from collect_sessions import parse_codex_session, parse_muse_session
from corpus_export_helpers import OLD, read_rows, run, write_jsonl
from session_corpus import CorpusCapture, redact
from test_corpus_export import make_gemini_home, make_t3_home, t3_row


@contextmanager
def capturing() -> Iterator[CorpusCapture]:
    capture = CorpusCapture()
    token = session_corpus._CAPTURE.set(capture)
    try:
        yield capture
    finally:
        session_corpus._CAPTURE.reset(token)


def muse_record(payload_type: str, payload: dict[str, Any], micros: int = 0) -> dict[str, Any]:
    return {
        "payload_type": payload_type,
        "payload": payload,
        "recorded_at": 1_700_000_000_000_000 + micros,
    }


def intent(text: str, micros: int) -> dict[str, Any]:
    body = {"model_messages": [{"content": [{"kind": "text", "text": text}]}]}
    return muse_record("runtime.user_intent.accepted", body, micros)


def test_muse_rows_carry_the_physical_journal_line(tmp_path: Path) -> None:
    path = tmp_path / "sessions" / "2026" / "11" / "22" / "s1" / "session.jsonl"
    write_jsonl(
        path,
        [
            muse_record("runtime.session.metadata", {"kind": "metadata", "record": {}}),
            intent("first question", 1_000_000),
            muse_record(
                "tool_batch.effect.started",
                {"run_id": "r", "record": {"tool_name": "bash", "call_id": "c"}},
                2_000_000,
            ),
            muse_record(
                "tool_batch.effect.terminal",
                {"run_id": "r", "record": {"outcome": {"kind": "completed"}}},
                3_000_000,
            ),
            intent("second question", 4_000_000),
        ],
    )
    with capturing() as capture:
        parse_muse_session(path, set(), False)
    assert [(row["text"], row["line"]) for row in capture.rows] == [
        ("first question", 2),
        ("second question", 5),
    ]


def _codex(*records: dict[str, Any]) -> list[dict[str, Any]]:
    meta = {"type": "session_meta", "payload": {"id": "c1", "cwd": "/repo"}}
    return [meta, *records]


def _event(kind: str, text: str) -> dict[str, Any]:
    return {"type": "event_msg", "timestamp": OLD, "payload": {"type": kind, "message": text}}


def _item(role: str, text: str) -> dict[str, Any]:
    kind = "output_text" if role == "assistant" else "input_text"
    payload = {"type": "message", "role": role, "content": [{"type": kind, "text": text}]}
    return {"type": "response_item", "payload": payload}


def test_codex_event_only_conversation_is_exported(tmp_path: Path) -> None:
    path = tmp_path / "rollout.jsonl"
    write_jsonl(
        path,
        _codex(_event("user_message", "why slow"), _event("agent_message", "12 ms vs 9 ms")),
    )
    with capturing() as capture:
        parse_codex_session(path, set(), False)
    assert [(row["role"], row["text"], row["line"]) for row in capture.rows] == [
        ("user", "why slow", 2),
        ("assistant", "12 ms vs 9 ms", 3),
    ]


def test_codex_rollout_with_items_and_events_exports_each_turn_once(tmp_path: Path) -> None:
    path = tmp_path / "rollout.jsonl"
    write_jsonl(
        path,
        _codex(
            _item("user", "why slow"),
            _event("user_message", "why slow"),
            _item("assistant", "12 ms vs 9 ms"),
            _event("agent_message", "12 ms vs 9 ms"),
        ),
    )
    with capturing() as capture:
        parse_codex_session(path, set(), False)
    assert [(row["role"], row["text"]) for row in capture.rows] == [
        ("user", "why slow"),
        ("assistant", "12 ms vs 9 ms"),
    ]


def test_codex_injected_user_event_is_not_exported(tmp_path: Path) -> None:
    path = tmp_path / "rollout.jsonl"
    write_jsonl(path, _codex(_event("user_message", "<system-reminder>x</system-reminder>")))
    with capturing() as capture:
        parse_codex_session(path, set(), False)
    assert capture.rows == []


def test_relative_t3_home_opens_the_database(tmp_path: Path) -> None:
    make_t3_home(tmp_path, [t3_row("m1", "user", {"text": "why slow"})])
    result = run(
        tmp_path, "--harness", "t3", "--all-conversations", "--t3-home", "t3-home",
        "--out", str(tmp_path / "report"), "--export-corpus", str(tmp_path / "c.jsonl"),
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    assert [row["text"] for row in read_rows(tmp_path / "c.jsonl")] == ["why slow"]


def test_gemini_record_with_a_non_string_type_is_skipped_not_fatal(tmp_path: Path) -> None:
    gemini = make_gemini_home(
        tmp_path,
        [
            {"type": [], "content": "bad", "timestamp": OLD},
            {"type": "USER_INPUT", "content": "question", "timestamp": OLD},
        ],
    )
    result = run(
        tmp_path, "--harness", "gemini", "--all-conversations", "--gemini-home", str(gemini),
        "--out", str(tmp_path / "report"), "--export-corpus", str(tmp_path / "c.jsonl"),
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    assert [row["text"] for row in read_rows(tmp_path / "c.jsonl")] == ["question"]


@pytest.mark.parametrize("name", ["inventory.json", "audit_manifest.json"])
def test_export_path_naming_a_report_file_is_refused(tmp_path: Path, name: str) -> None:
    report = tmp_path / "report"
    result = run(
        tmp_path, "--all-conversations", "--out", str(report),
        "--export-corpus", str(report / name),
    )  # fmt: skip
    assert result.returncode == 2
    assert "report file" in result.stderr
    assert not (report / name).exists()


def test_export_path_inside_the_transcripts_directory_is_refused(tmp_path: Path) -> None:
    report = tmp_path / "report"
    result = run(
        tmp_path, "--all-conversations", "--out", str(report),
        "--export-corpus", str(report / "transcripts" / "c.jsonl"),
    )  # fmt: skip
    assert result.returncode == 2
    assert "transcripts" in result.stderr


@pytest.mark.parametrize(
    "secret",
    [
        "eyJhbGciOiJIUzI1NiJ9." + "p" * 12,
        "Authorization: Bearer abc/def+ghi=" + "k" * 20,
        "bearer " + "ab/c" * 8,
    ],
)
def test_redact_covers_short_header_jwts_and_slash_bearer_values(secret: str) -> None:
    redacted = redact(f"before {secret} after")
    assert "[REDACTED]" in redacted
    assert redacted.endswith("[REDACTED] after")
    assert secret.split()[-1] not in redacted


def test_redact_keeps_prose_that_only_mentions_bearer() -> None:
    text = "the bearer of the token is the user"
    assert redact(text) == text


def test_corpus_rows_keep_json_loadable_after_redaction(tmp_path: Path) -> None:
    gemini = make_gemini_home(
        tmp_path,
        [
            {
                "type": "USER_INPUT",
                "content": "key eyJhbGciOiJIUzI1NiJ9.abcdefghijkl",
                "timestamp": OLD,
            }
        ],
    )
    result = run(
        tmp_path, "--harness", "gemini", "--all-conversations", "--gemini-home", str(gemini),
        "--out", str(tmp_path / "report"), "--export-corpus", str(tmp_path / "c.jsonl"),
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    assert (
        json.loads((tmp_path / "c.jsonl").read_text(encoding="utf-8"))["text"] == "key [REDACTED]"
    )
