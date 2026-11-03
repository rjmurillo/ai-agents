"""Tests for scripts/metrics/convert_copilot.py with synthetic Copilot events."""

from __future__ import annotations

import json
import os
import stat
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.failure_classifier import events_from_records
from scripts.failure_classifier.transcript import stop_feedback_count
from scripts.metrics import convert_copilot as cc

TS = "2026-11-01T20:05:15.237Z"


def _ev(kind: str, ts: str | None = TS, **data: Any) -> dict[str, Any]:
    event: dict[str, Any] = {"type": kind, "data": data, "id": "e"}
    if ts is not None:
        event["timestamp"] = ts
    return event


def _start(call: str, tool: str, **arguments: Any) -> dict[str, Any]:
    return _ev("tool.execution_start", toolCallId=call, toolName=tool, arguments=arguments)


def _ok(call: str, text: str) -> dict[str, Any]:
    return _ev("tool.execution_complete", toolCallId=call, success=True, result={"content": text})


def _fail(call: str, code: str, message: str) -> dict[str, Any]:
    return _ev(
        "tool.execution_complete",
        toolCallId=call,
        success=False,
        error={"code": code, "message": message},
    )


def _convert(*events: object) -> tuple[list[dict[str, Any]], cc.Counts]:
    return cc.convert_events(events)


def test_success_pairs_through_classifier() -> None:
    records, counts = _convert(_start("c1", "view", path="a.py"), _ok("c1", "file body"))
    (event,) = events_from_records(records)
    assert event.ok is True
    assert (counts.tool_calls, counts.errored) == (1, 0)
    assert records[1]["message"]["content"][0]["content"] == "file body"


def test_failure_is_error_with_original_text() -> None:
    text = "Unhandled error: Error: ENOENT: no such file or directory, open '/x'"
    records, counts = _convert(_start("c1", "edit", path="/x"), _fail("c1", "failure", text))
    (event,) = events_from_records(records)
    assert event.ok is False
    assert event.error == text
    assert counts.errored == 1


def test_shell_tool_maps_to_bash_with_command() -> None:
    records, _ = _convert(
        _start("c1", "bash", command="git status", description="d", mode="sync"),
        _ok("c1", "ok"),
    )
    block = records[0]["message"]["content"][0]
    assert block["name"] == "Bash"
    assert block["input"] == {"command": "git status"}
    (event,) = events_from_records(records)
    assert event.tool.lower() == "bash"


def test_shell_without_command_gets_empty_string() -> None:
    records, _ = _convert(_start("c1", "powershell"), _ok("c1", ""))
    assert records[0]["message"]["content"][0]["input"] == {"command": ""}


def test_non_shell_tool_keeps_name_and_arguments() -> None:
    records, _ = _convert(_start("c1", "view", path="a.py"))
    block = records[0]["message"]["content"][0]
    assert (block["name"], block["input"]) == ("view", {"path": "a.py"})


def test_denial_kept_as_error_with_original_text() -> None:
    text = (
        "Permission denied because no interactive user response was available. "
        "Retry in an interactive session so the user can approve it."
    )
    records, counts = _convert(
        _start("c1", "bash", command="git add ."), _fail("c1", "denied", text)
    )
    block = records[1]["message"]["content"][0]
    assert block["is_error"] is True
    assert block["content"] == text
    assert counts.errored == 1


def test_human_prompt_uses_content_not_transformed() -> None:
    records, counts = _convert(
        _ev("user.message", content="fix the bug", transformedContent="<ctx>fix the bug</ctx>")
    )
    (record,) = records
    assert record["promptSource"] == "typed"
    assert record["message"]["content"] == "fix the bug"
    assert counts.human_turns == 1


@pytest.mark.parametrize("kind", ["system.message", "system.notification", "hook.start"])
def test_injected_events_are_not_human_turns(kind: str) -> None:
    records, counts = _convert(_ev(kind, content="You are the GitHub Copilot CLI"))
    assert records == []
    assert counts.human_turns == 0


@pytest.mark.parametrize("content", ["", "   ", None, 5])
def test_empty_or_bad_user_content_is_not_a_turn(content: object) -> None:
    records, counts = _convert(_ev("user.message", content=content))
    assert records == []
    assert counts.human_turns == 0


def test_agent_prose_becomes_text_block() -> None:
    records, _ = _convert(_ev("assistant.message", content="Done.", toolRequests=[]))
    assert records == [
        {
            "type": "assistant",
            "timestamp": TS,
            "message": {"content": [{"type": "text", "text": "Done."}]},
        }
    ]


def test_empty_assistant_message_emits_nothing() -> None:
    records, _ = _convert(_ev("assistant.message", content="", toolRequests=[{"x": 1}]))
    assert records == []


def _stop_end(**extra: Any) -> dict[str, Any]:
    return _ev("hook.end", hookType="agentStop", success=True, **extra)


def test_hook_block_on_emits_feedback_record() -> None:
    records, counts = _convert(_stop_end(output={"decision": "block", "reason": "run tests"}))
    (record,) = records
    assert record["message"]["content"] == "Stop hook feedback: run tests"
    assert "toolUseResult" not in record
    assert counts.hook_blocks == 1
    assert stop_feedback_count(records) == 1


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"output": {}},
        {"output": {"decision": "approve", "reason": "x"}},
        {"output": {"decision": "block"}},
        {"output": {"decision": "block", "reason": "  "}},
        {"output": "block"},
    ],
)
def test_hook_block_off_emits_nothing(extra: dict[str, Any]) -> None:
    records, counts = _convert(_stop_end(**extra))
    assert records == []
    assert counts.hook_blocks == 0


def test_non_stop_hook_with_block_output_is_ignored() -> None:
    event = _ev("hook.end", hookType="preToolUse", output={"decision": "block", "reason": "r"})
    assert _convert(event)[0] == []


def test_every_record_carries_timestamp_and_missing_is_skipped() -> None:
    records, counts = _convert(
        _ev("user.message", content="hi"),
        _ev("user.message", ts=None, content="no ts"),
        "not an event",
        _start("c1", "view", path="a"),
        _ok("c1", "t"),
    )
    assert [r["timestamp"] for r in records] == [TS, TS, TS]
    assert counts.skipped == 2


def test_tool_events_without_ids_are_dropped() -> None:
    records, _ = _convert(
        _ev("tool.execution_start", toolName="view"), _ev("tool.execution_complete")
    )
    assert records == []


def test_result_text_falls_back_to_empty() -> None:
    records, _ = _convert(
        _start("c1", "view"), _ev("tool.execution_complete", toolCallId="c1", success=True)
    )
    assert records[1]["message"]["content"][0]["content"] == ""


def _write_session(root: Path, name: str, events: list[object]) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    lines = [e if isinstance(e, str) else json.dumps(e) for e in events]
    (folder / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _session_events() -> list[object]:
    return [
        _ev("user.message", content="go"),
        _start("c1", "bash", command="ls"),
        _ok("c1", "a"),
        _start("c2", "bash", command="pwd"),
        _fail("c2", "denied", "Permission denied because x"),
        "{not json",
    ]


def test_run_writes_private_file_and_counts(tmp_path: Path) -> None:
    src, out = tmp_path / "src", tmp_path / "out"
    _write_session(src, "sess-1", _session_events())
    counts = cc.run(str(src / "*" / "events.jsonl"), out, date(2026, 10, 3))
    target = out / "sess-1.jsonl"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert (counts.files, counts.sessions, counts.tool_calls) == (1, 1, 2)
    assert (counts.errored, counts.human_turns, counts.skipped) == (1, 1, 1)
    records = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert [e.ok for e in events_from_records(records)] == [True, False]


def test_run_skips_sessions_before_since(tmp_path: Path) -> None:
    src, out = tmp_path / "src", tmp_path / "out"
    _write_session(src, "sess-1", _session_events())
    counts = cc.run(str(src / "*" / "events.jsonl"), out, date(2026, 11, 2))
    assert (counts.files, counts.sessions, counts.skipped) == (1, 0, 2)  # 1 bad line + 1 session
    assert list(out.iterdir()) == []


def test_run_skips_unsafe_session_dir_and_empty_session(tmp_path: Path) -> None:
    src, out = tmp_path / "src", tmp_path / "out"
    _write_session(src, "bad name", _session_events())
    _write_session(src, "empty-1", [_ev("session.start")])
    counts = cc.run(str(src / "*" / "events.jsonl"), out, date(2026, 10, 3))
    assert (counts.files, counts.sessions) == (2, 0)
    assert counts.skipped >= 2


def test_run_replaces_existing_output(tmp_path: Path) -> None:
    src, out = tmp_path / "src", tmp_path / "out"
    _write_session(src, "sess-1", _session_events())
    pattern = str(src / "*" / "events.jsonl")
    cc.run(pattern, out, date(2026, 10, 3))
    cc.run(pattern, out, date(2026, 10, 3))
    assert len((out / "sess-1.jsonl").read_text(encoding="utf-8").splitlines()) == 5


def test_main_refuses_out_dir_inside_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".git").mkdir()
    code = cc.main(
        [
            "--src-glob",
            str(tmp_path / "*"),
            "--out-dir",
            str(tmp_path / "out"),
            "--since",
            "2026-10-03",
        ]
    )
    assert code == cc.EXIT_CONFIG
    assert "inside a git repository" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_main_prints_counts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "src"
    _write_session(src, "sess-1", _session_events())
    code = cc.main(
        [
            "--src-glob",
            str(src / "*" / "events.jsonl"),
            "--out-dir",
            str(tmp_path / "out"),
            "--since",
            "2026-10-03",
        ]
    )
    out = capsys.readouterr().out
    assert code == cc.EXIT_OK
    assert "sessions=1" in out and "tool_calls=2" in out and "errored_results=1" in out


def test_run_skips_file_older_than_since_without_reading(tmp_path: Path) -> None:
    src, out = tmp_path / "src", tmp_path / "out"
    _write_session(src, "sess-1", _session_events())
    old = src / "sess-1" / "events.jsonl"
    os.utime(old, (1_600_000_000, 1_600_000_000))
    counts = cc.run(str(src / "*" / "events.jsonl"), out, date(2026, 10, 3))
    assert (counts.files, counts.sessions, counts.skipped) == (1, 0, 1)


def test_run_creates_out_dir_0700_and_tightens_existing(tmp_path: Path) -> None:
    pattern = str(tmp_path / "none" / "*" / "events.jsonl")
    fresh = tmp_path / "fresh"
    cc.run(pattern, fresh, date(2026, 10, 3))
    assert stat.S_IMODE(fresh.stat().st_mode) == 0o700
    loose = tmp_path / "loose"
    loose.mkdir()
    loose.chmod(0o755)
    cc.run(pattern, loose, date(2026, 10, 3))
    assert stat.S_IMODE(loose.stat().st_mode) == 0o700


def test_lone_surrogate_in_input_does_not_crash_the_write(tmp_path: Path) -> None:
    src, out = tmp_path / "src", tmp_path / "out"
    events = _session_events()
    events.append(_ev("user.message", content="bad \ud800 text"))
    _write_session(src, "sess-1", events)
    counts = cc.run(str(src / "*" / "events.jsonl"), out, date(2026, 10, 3))
    assert counts.sessions == 1
    raw = (out / "sess-1.jsonl").read_bytes()
    assert raw.isascii()
    assert b"ud800" in raw
