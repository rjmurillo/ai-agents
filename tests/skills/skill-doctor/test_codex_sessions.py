"""Codex rollout parsing, provider termination, and the idle window (issues 7184, 7189).

Every fixture is synthetic. Never copy a real session file here.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from collect_sessions import parse_claude_session, parse_codex_session
from session_test_helpers import run_collector, write_jsonl

ROOTS = ["claude", "copilot-cli"]


def _meta(cwd="/repo"):
    return {"type": "session_meta", "payload": {"id": "codex-1", "cwd": cwd}}


def _message(role, text, kind=None):
    kind = kind or ("output_text" if role == "assistant" else "input_text")
    return {
        "type": "response_item",
        "payload": {"type": "message", "role": role, "content": [{"type": kind, "text": text}]},
    }


def _tool_call():
    return {
        "type": "response_item",
        "payload": {"type": "custom_tool_call", "name": "exec", "input": "ls"},
    }


def _tool_output():
    return {
        "type": "response_item",
        "payload": {"type": "custom_tool_call_output", "output": "ok"},
    }


def _event(kind, **extra):
    return {"type": "event_msg", "payload": {"type": kind, **extra}}


def _current_rollout(assistant_messages=2):
    records = [_meta(), _message("developer", "", "input_text"), _message("user", "do work")]
    for index in range(assistant_messages):
        records.extend([_message("assistant", f"step {index}"), _tool_call(), _tool_output()])
    records.append(_event("item_completed", item={"type": "CommandExecution"}))
    records.append(_event("task_complete", last_agent_message=None))
    return records


def _parse(tmp_path, records, name="rollout.jsonl"):
    path = tmp_path / name
    write_jsonl(path, records)
    return parse_codex_session(path, set(), False)


def test_current_rollout_counts_response_item_turns(tmp_path):
    _, stats, _, _ = _parse(tmp_path, _current_rollout(assistant_messages=3))

    assert stats["assistant_turns"] == 3
    assert stats["user_turns"] == 1
    assert stats["tool_calls"] == 3


def test_developer_messages_are_not_counted(tmp_path):
    records = [_meta(), _message("developer", "policy text", "input_text")]
    _, stats, _, _ = _parse(tmp_path, records)

    assert stats["assistant_turns"] == 0
    assert stats["user_turns"] == 0


def test_older_rollout_counts_each_turn_once(tmp_path):
    records = [
        _meta(),
        _event("user_message", message="hi"),
        _message("user", "hi"),
        _event("agent_message", message="a1"),
        _message("assistant", "a1"),
        _tool_call(),
        _tool_output(),
        _event("agent_message", message="a2"),
        _message("assistant", "a2"),
    ]
    _, stats, _, _ = _parse(tmp_path, records)

    assert stats["assistant_turns"] == 2
    assert stats["user_turns"] == 1


def test_event_only_rollout_still_counts(tmp_path):
    records = [
        _meta(),
        _event("user_message", message="hi"),
        _event("agent_message", message="a1"),
        _tool_call(),
    ]
    _, stats, _, _ = _parse(tmp_path, records)

    assert stats["assistant_turns"] == 1
    assert stats["user_turns"] == 1


def test_response_item_agent_message_text_reaches_transcript(tmp_path):
    child = {
        "type": "response_item",
        "payload": {
            "type": "agent_message",
            "author": "/root/child",
            "recipient": "/root",
            "content": [{"type": "input_text", "text": "FINAL_ANSWER child finished"}],
        },
    }
    _, _, entries, _ = _parse(tmp_path, _current_rollout(1) + [child])

    assert any("FINAL_ANSWER child finished" in text for _, text in entries)


def _usage_limit_tail(code="usage_limit_exceeded"):
    return [
        _event(
            "task_complete",
            last_agent_message=None,
            error={"message": "Your workspace is out of credits.", "codex_error_info": code},
        )
    ]


def test_codex_terminal_error_sets_terminated_by_and_ends_transcript(tmp_path):
    records = _current_rollout(2)[:-1] + _usage_limit_tail()
    _, stats, entries, _ = _parse(tmp_path, records)

    assert stats["terminated_by"] == "usage_limit_exceeded"
    role, text = entries[-1]
    assert role == "terminated"
    assert "usage_limit_exceeded" in text
    assert "out of credits" in text


def test_codex_server_overloaded_is_recorded(tmp_path):
    _, stats, _, _ = _parse(
        tmp_path, _current_rollout(1)[:-1] + _usage_limit_tail("server_overloaded")
    )

    assert stats["terminated_by"] == "server_overloaded"


def test_codex_structured_error_info_uses_its_key(tmp_path):
    tail = [
        _event(
            "task_complete",
            error={"message": "boom", "codex_error_info": {"http_connection_failed": {"x": 1}}},
        )
    ]
    _, stats, _, _ = _parse(tmp_path, _current_rollout(1)[:-1] + tail)

    assert stats["terminated_by"] == "http_connection_failed"


def test_codex_clean_completion_has_no_termination(tmp_path):
    _, stats, entries, _ = _parse(tmp_path, _current_rollout(1))

    assert stats["terminated_by"] is None
    assert all(role != "terminated" for role, _ in entries)


def test_codex_later_clean_turn_clears_earlier_error(tmp_path):
    records = (
        _current_rollout(1)[:-1]
        + _usage_limit_tail()
        + [_message("assistant", "resumed"), _event("task_complete", last_agent_message="done")]
    )
    _, stats, _, _ = _parse(tmp_path, records)

    assert stats["terminated_by"] is None


def _claude_record(role, content, **extra):
    return {
        "type": role,
        "sessionId": "s1",
        "cwd": "/repo",
        "timestamp": "2026-11-09T10:00:00Z",
        "uuid": f"u-{role}-{len(json.dumps(content))}-{extra.get('uuid', '')}",
        "message": {"role": role, "content": content, **extra.pop("message", {})},
        **extra,
    }


def _claude_limit_session():
    return [
        _claude_record("user", [{"type": "text", "text": "go"}]),
        _claude_record(
            "assistant",
            [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}],
        ),
        _claude_record(
            "assistant",
            [{"type": "text", "text": "You've hit your weekly limit · resets Nov 9"}],
            isApiErrorMessage=True,
            error="rate_limit",
            apiError="usage_limit_reached",
            apiErrorStatus=429,
            uuid="err",
        ),
    ]


def test_claude_usage_limit_error_sets_terminated_by(tmp_path):
    path = tmp_path / "claude.jsonl"
    write_jsonl(path, _claude_limit_session())
    _, stats, entries, _ = parse_claude_session(path, set(), False)

    assert stats["terminated_by"] == "usage_limit_reached"
    assert entries[-1][0] == "terminated"
    assert "weekly limit" in entries[-1][1]


def test_claude_api_error_followed_by_normal_assistant_turn_is_not_terminal(tmp_path):
    records = _claude_limit_session() + [
        _claude_record("assistant", [{"type": "text", "text": "recovered"}], uuid="ok")
    ]
    path = tmp_path / "claude.jsonl"
    write_jsonl(path, records)
    _, stats, _, _ = parse_claude_session(path, set(), False)

    assert stats["terminated_by"] is None


def test_claude_without_api_error_has_no_termination(tmp_path):
    path = tmp_path / "claude.jsonl"
    write_jsonl(path, _claude_limit_session()[:2])
    _, stats, _, _ = parse_claude_session(path, set(), False)

    assert stats["terminated_by"] is None


def _iso(delta):
    return (datetime.now(timezone.utc) - delta).isoformat().replace("+00:00", "Z")


def _write_rollout(codex_home, name, age, records_fn=_current_rollout):
    """Write a rollout whose record timestamps and mtime sit `age` in the past."""
    stamp = _iso(age)
    records = [{**record, "timestamp": stamp} for record in records_fn()]
    path = codex_home / "sessions" / "2026" / "11" / "09" / f"rollout-{name}.jsonl"
    write_jsonl(path, records)
    when = (datetime.now(timezone.utc) - age).timestamp()
    os.utime(path, (when, when))
    return path


def _collect(tmp_path, root, *extra):
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    result = run_collector(
        tmp_path,
        tmp_path / "copilot",
        "--harness",
        "codex",
        "--codex-home",
        str(tmp_path / "codex"),
        "--repo",
        str(repo),
        *extra,
        root=root,
    )
    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text())
    return result, inventory


def _codex_cwd_records(cwd):
    def build():
        records = _current_rollout()
        records[0] = _meta(cwd)
        return records

    return build


@pytest.mark.parametrize("root", ROOTS)
def test_current_rollout_is_scoreable_through_the_collector(tmp_path, root):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_rollout(tmp_path / "codex", "old", timedelta(hours=3), _codex_cwd_records(str(repo)))

    _, inventory = _collect(tmp_path, root)

    assert inventory["stats"]["sessions_considered"] == 1


@pytest.mark.parametrize("root", ROOTS)
def test_idle_window_skips_live_session_by_default_and_counts_it(tmp_path, root):
    repo = tmp_path / "repo"
    repo.mkdir()
    build = _codex_cwd_records(str(repo))
    _write_rollout(tmp_path / "codex", "live", timedelta(minutes=1), build)
    _write_rollout(tmp_path / "codex", "done", timedelta(hours=2), build)

    _, inventory = _collect(tmp_path, root)

    assert inventory["stats"]["sessions_considered"] == 1
    assert inventory["stats"]["sessions_skipped_idle"] == 1


@pytest.mark.parametrize("root", ROOTS)
def test_min_idle_minutes_zero_keeps_live_session(tmp_path, root):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_rollout(tmp_path / "codex", "live", timedelta(minutes=1), _codex_cwd_records(str(repo)))

    _, inventory = _collect(tmp_path, root, "--min-idle-minutes", "0")

    assert inventory["stats"]["sessions_considered"] == 1
    assert inventory["stats"]["sessions_skipped_idle"] == 0


@pytest.mark.parametrize("root", ROOTS)
def test_terminated_session_is_reported_in_inventory_and_transcript(tmp_path, root):
    repo = tmp_path / "repo"
    repo.mkdir()

    def build():
        records = _current_rollout(2)[:-1] + _usage_limit_tail()
        records[0] = _meta(str(repo))
        return records

    _write_rollout(tmp_path / "codex", "cut", timedelta(hours=2), build)

    _, inventory = _collect(tmp_path, root)

    session = inventory["sessions"][0]
    assert session["stats"]["terminated_by"] == "usage_limit_exceeded"
    transcript = Path(session["transcript_path"]).read_text()
    assert "- terminated by: usage_limit_exceeded" in transcript
    assert transcript.rstrip().splitlines()[-1].startswith("[terminated]")


def test_negative_min_idle_minutes_is_a_usage_error(tmp_path):
    result = run_collector(
        tmp_path, tmp_path / "copilot", "--harness", "codex", "--min-idle-minutes", "-5"
    )

    assert result.returncode == 2


def _now_minus(**kwargs):
    return datetime.now(timezone.utc) - timedelta(**kwargs)


# Factories keep the parametrize ids stable, so xdist workers collect identical test ids.
_TIMESTAMP_CASES = {
    "missing": (lambda: None, False),
    "garbage-string": (lambda: "not a timestamp", False),
    "boolean": (lambda: True, False),
    "recent-iso-z": (lambda: _iso(timedelta(minutes=1)), True),
    "old-iso-z": (lambda: _iso(timedelta(hours=1)), False),
    "recent-nine-digit-fraction": (
        lambda: _now_minus(minutes=1).strftime("%Y-%m-%dT%H:%M:%S.123456789Z"),
        True,
    ),
    "recent-epoch-seconds": (lambda: _now_minus(minutes=2).timestamp(), True),
    "old-epoch-milliseconds": (lambda: _now_minus(hours=2).timestamp() * 1000, False),
    "recent-naive-iso": (lambda: _now_minus(minutes=2).replace(tzinfo=None).isoformat(), True),
}


@pytest.mark.parametrize("case", sorted(_TIMESTAMP_CASES))
def test_is_live_session_handles_timestamp_shapes(case):
    from session_common import is_live_session

    build, expected = _TIMESTAMP_CASES[case]

    assert is_live_session({"last_ts": build()}, 15.0) is expected


def test_is_live_session_never_skips_when_window_is_zero():
    from session_common import is_live_session

    assert is_live_session({"last_ts": _iso(timedelta(seconds=1))}, 0) is False
