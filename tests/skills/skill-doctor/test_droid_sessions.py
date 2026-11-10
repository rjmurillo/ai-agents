"""Factory Droid session collection for skill-doctor (issue 7188).

Fixtures are synthetic. Record shapes follow the on-disk Droid store layout:
``<factory-home>/sessions/<encoded-cwd>/<uuid>.jsonl`` with ``session_start``,
``message``, ``agent_turn_outcome`` and bookkeeping records.
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from collect_sessions import find_droid_session_files, parse_droid_session
from session_test_helpers import write_jsonl


def _start(cwd="/tmp/repo", session_id="droid-1", **extra):
    return {"type": "session_start", "id": session_id, "cwd": cwd, "version": 2, **extra}


def _message(role, blocks, message_id, timestamp):
    return {
        "type": "message",
        "id": message_id,
        "timestamp": timestamp,
        "message": {"role": role, "content": blocks},
    }


def _outcome(reason):
    return {
        "type": "agent_turn_outcome",
        "turnId": "turn-1",
        "reason": reason,
        "resultKind": "text",
    }


def _working_session(cwd="/tmp/repo", session_id="droid-1", **start_extra):
    return [
        _start(cwd, session_id, **start_extra),
        _message(
            "user", [{"type": "text", "text": "Improve the skill"}], "m1", "2026-11-01T10:00:00Z"
        ),
        _message(
            "assistant",
            [
                {"type": "thinking", "thinking": "plan"},
                {"type": "text", "text": "Reading it."},
                {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "alpha"}},
                {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "/a"}},
            ],
            "m2",
            "2026-11-01T10:00:01Z",
        ),
        _message(
            "user",
            [{"type": "tool_result", "tool_use_id": "t2", "is_error": True, "content": "denied"}],
            "m3",
            "2026-11-01T10:00:02Z",
        ),
        _message(
            "assistant",
            [{"type": "tool_use", "id": "t3", "name": "Create", "input": {"file_path": "/b"}}],
            "m4",
            "2026-11-01T10:00:03Z",
        ),
        _outcome("completed"),
    ]


def _parse(tmp_path, records, include_subagents=False):
    path = tmp_path / "droid-1.jsonl"
    write_jsonl(path, records)
    return parse_droid_session(path, {"alpha"}, include_subagents)


def test_parses_meta_stats_skills_and_edits(tmp_path):
    meta, stats, entries, skills = _parse(tmp_path, _working_session())

    assert meta["id"] == "droid-1"
    assert meta["cwd"] == "/tmp/repo"
    assert meta["originator"] == "droid"
    assert stats["user_turns"] == 1
    assert stats["assistant_turns"] == 2
    assert stats["tool_calls"] == 3
    assert stats["error_outputs"] == 1
    assert stats["has_code_edits"] is True
    assert stats["first_ts"] == "2026-11-01T10:00:00Z"
    assert stats["last_ts"] == "2026-11-01T10:00:03Z"
    assert skills == ["alpha"]
    assert ("user", "Improve the skill") in entries
    assert stats.get("terminated_by") is None


def test_tool_name_alone_marks_apply_patch_as_code_edit(tmp_path):
    records = [
        _start(),
        _message(
            "assistant",
            [{"type": "tool_use", "id": "t1", "name": "ApplyPatch", "input": {"patch": "x"}}],
            "m1",
            "2026-11-01T10:00:00Z",
        ),
    ]

    _meta, stats, _entries, _skills = _parse(tmp_path, records)

    assert stats["has_code_edits"] is True


def test_read_only_session_has_no_code_edits(tmp_path):
    records = [
        _start(),
        _message(
            "assistant",
            [{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/a"}}],
            "m1",
            "2026-11-01T10:00:00Z",
        ),
    ]

    _meta, stats, _entries, _skills = _parse(tmp_path, records)

    assert stats["has_code_edits"] is False


def test_child_session_is_skipped_unless_subagents_requested(tmp_path):
    records = _working_session(session_id="child-1", callingSessionId="parent-1")

    assert _parse(tmp_path, records) is None
    meta, _stats, _entries, _skills = _parse(tmp_path, records, include_subagents=True)
    assert meta["thread_source"] == "subagent"


def test_repeated_assistant_message_id_counts_one_turn(tmp_path):
    block = [{"type": "text", "text": "same"}]
    records = [
        _start(),
        _message("assistant", block, "dup", "2026-11-01T10:00:00Z"),
        _message("assistant", block, "dup", "2026-11-01T10:00:01Z"),
    ]

    _meta, stats, _entries, _skills = _parse(tmp_path, records)

    assert stats["assistant_turns"] == 1


def test_missing_cwd_leaves_cwd_unset(tmp_path):
    records = [{"type": "session_start", "id": "no-cwd"}, *_working_session()[1:]]

    meta, _stats, _entries, _skills = _parse(tmp_path, records)

    assert meta["id"] == "no-cwd"
    assert meta["cwd"] is None


def test_empty_file_has_no_scoreable_activity(tmp_path):
    path = tmp_path / "empty-id.jsonl"
    path.write_text("", encoding="utf-8")

    meta, stats, entries, skills = parse_droid_session(path, {"alpha"}, False)

    assert meta["id"] == "empty-id"
    assert meta["cwd"] is None
    assert stats["assistant_turns"] == 0
    assert stats["tool_calls"] == 0
    assert entries == []
    assert skills == []


def test_malformed_lines_and_unknown_records_are_skipped(tmp_path):
    path = tmp_path / "mixed.jsonl"
    lines = [json.dumps(record) for record in _working_session()]
    lines.insert(1, "{not json")
    lines.insert(2, json.dumps({"type": "todo_state", "todos": []}))
    lines.insert(3, json.dumps({"type": "message", "id": "bad", "message": "not a dict"}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _meta, stats, _entries, _skills = parse_droid_session(path, {"alpha"}, False)

    assert stats["tool_calls"] == 3


def test_missing_file_returns_none(tmp_path):
    assert parse_droid_session(tmp_path / "gone.jsonl", set(), False) is None


@pytest.mark.parametrize(
    ("final_outcome", "expected"),
    [
        ("model_usage_exhausted", "model_usage_exhausted"),
        ("completed", None),
        ("cancelled", None),
        ("model_authentication_failed", None),
    ],
)
def test_terminated_by_follows_final_turn_outcome(tmp_path, final_outcome, expected):
    records = [*_working_session()[:-1], _outcome(final_outcome)]

    _meta, stats, _entries, _skills = _parse(tmp_path, records)

    assert stats.get("terminated_by") == expected


def test_usage_exhausted_turn_followed_by_completed_turn_is_not_terminated(tmp_path):
    records = [*_working_session()[:-1], _outcome("model_usage_exhausted"), _outcome("completed")]

    _meta, stats, _entries, _skills = _parse(tmp_path, records)

    assert stats.get("terminated_by") is None


@pytest.mark.parametrize(
    "text",
    [
        "You have reached your weekly limit. Upgrade your plan to continue.",
        "Usage limit reached for this billing period.",
        "Monthly usage limit exceeded.",
    ],
)
def test_limit_message_as_final_message_sets_terminated_by(tmp_path, text):
    records = [
        *_working_session()[:-1],
        _message("assistant", [{"type": "text", "text": text}], "m9", "2026-11-01T10:00:09Z"),
    ]

    _meta, stats, _entries, _skills = _parse(tmp_path, records)

    assert stats["terminated_by"] == "usage_limit_exceeded"


def test_limit_notice_inside_a_long_final_report_is_not_termination(tmp_path):
    report = "You have reached your weekly limit. " + "Details follow. " * 40
    assert len(report) > 400
    records = [
        *_working_session()[:-1],
        _message("assistant", [{"type": "text", "text": report}], "m9", "2026-11-01T10:00:09Z"),
    ]

    _meta, stats, _entries, _skills = _parse(tmp_path, records)

    assert stats.get("terminated_by") is None


def test_limit_message_that_is_not_final_is_not_termination(tmp_path):
    records = [
        *_working_session()[:-1],
        _message(
            "assistant",
            [{"type": "text", "text": "You have reached your weekly limit."}],
            "m8",
            "2026-11-01T10:00:08Z",
        ),
        _message("user", [{"type": "text", "text": "ok, continue"}], "m9", "2026-11-01T10:00:09Z"),
        _outcome("completed"),
    ]

    _meta, stats, _entries, _skills = _parse(tmp_path, records)

    assert stats.get("terminated_by") is None


def test_limit_message_after_an_earlier_completed_turn_is_termination(tmp_path):
    records = [
        *_working_session(),
        _message("user", [{"type": "text", "text": "continue"}], "m8", "2026-11-01T10:00:08Z"),
        _message(
            "assistant",
            [{"type": "text", "text": "You have reached your weekly limit."}],
            "m9",
            "2026-11-01T10:00:09Z",
        ),
    ]

    _meta, stats, _entries, _skills = _parse(tmp_path, records)

    assert stats["terminated_by"] == "usage_limit_exceeded"


def test_exhausted_turn_is_cleared_when_the_session_resumes(tmp_path):
    records = [
        *_working_session()[:-1],
        _outcome("model_usage_exhausted"),
        _message("user", [{"type": "text", "text": "try again"}], "m8", "2026-11-01T10:00:08Z"),
        _message("assistant", [{"type": "text", "text": "Done."}], "m9", "2026-11-01T10:00:09Z"),
    ]

    _meta, stats, _entries, _skills = _parse(tmp_path, records)

    assert stats.get("terminated_by") is None


def test_empty_user_message_around_an_exhausted_turn_keeps_termination(tmp_path):
    records = [
        *_working_session()[:-1],
        _message("user", [], "m8", "2026-11-01T10:00:08Z"),
        _outcome("model_usage_exhausted"),
        _message("user", [], "m9", "2026-11-01T10:00:09Z"),
    ]

    _meta, stats, _entries, _skills = _parse(tmp_path, records)

    assert stats["terminated_by"] == "model_usage_exhausted"


@pytest.mark.parametrize(
    ("role", "block"),
    [
        ("user", {"type": "text", "text": "You have reached your weekly limit."}),
        (
            "user",
            {"type": "tool_result", "tool_use_id": "t3", "content": "429: rate limit exceeded"},
        ),
        ("assistant", {"type": "text", "text": "Added a rate limiter; the load test hit it."}),
        ("assistant", {"type": "text", "text": "Fixed the 429s: the client hit the rate limit."}),
    ],
)
def test_limit_wording_outside_an_assistant_notice_is_not_termination(tmp_path, role, block):
    records = [
        *_working_session()[:-1],
        _message(role, [block], "m9", "2026-11-01T10:00:09Z"),
    ]

    _meta, stats, _entries, _skills = _parse(tmp_path, records)

    assert stats.get("terminated_by") is None


def test_finder_matches_session_jsonl_inside_cutoff_only(tmp_path):
    home = tmp_path / "factory"
    fresh = home / "sessions" / "-tmp-repo" / "fresh.jsonl"
    stale = home / "sessions" / "-tmp-repo" / "stale.jsonl"
    settings = home / "sessions" / "-tmp-repo" / "fresh.settings.json"
    stray = home / "sessions" / "loose.jsonl"
    for path in (fresh, stale, settings, stray):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    old = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
    os.utime(stale, (old, old))
    cutoff = datetime.now(timezone.utc) - timedelta(days=45)

    found = [path for _mtime, path in find_droid_session_files(home, cutoff)]

    assert found == [fresh]


def test_finder_returns_nothing_without_sessions_directory(tmp_path):
    cutoff = datetime.now(timezone.utc) - timedelta(days=45)

    assert find_droid_session_files(tmp_path / "absent", cutoff) == []
