"""prepare and tally: exit 3, follow-up push split, subagent handbacks. Synthetic data only."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from replies_helpers import (
    CONTROL_TOKEN,
    assistant_text,
    assistant_tool,
    plant_control,
    prepare_args,
    prepare_ok,
    replies_prepare,
    replies_tally,
    run_cli,
    simple_session,
    tool_result,
    user,
    write_child,
    write_session,
)

IO_ERROR = {"error": "io", "message": "read_or_write_failed"}
CANNOT_DENY_WRITE = sys.platform == "win32" or getattr(os, "geteuid", lambda: 1)() == 0
PUSH = "go ahead please"
NEUTRAL = "synthetic neutral remark about colors"
NUDGE = "continue"
AUTHORITY = "you already have my approval"
SHARED_BRIEF = "synthetic shared delegated brief repeated across siblings for fingerprint"
HOST_CONTINUE = "Continue where you left off."


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "projects" / "proj-a"


def thread(prompt: str, followups: list[str], start: float = 10.0) -> list[dict[str, Any]]:
    """A prompt and reply, then each typed follow-up answered by a reply."""
    recs = [user(prompt, start), assistant_text("synthetic reply 0", start + 1)]
    at = start + 1
    for number, text in enumerate(followups, start=1):
        recs += [user(text, at + 1), assistant_text(f"synthetic reply {number}", at + 2)]
        at += 2
    return recs


def prepared_payload(
    capsys: pytest.CaptureFixture[str], store: Path, tmp_path: Path
) -> dict[str, Any]:
    plant_control(store)
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    return payload


def add_child(
    store: Path,
    parent: str,
    name: str,
    prompt: str,
    replied: bool = True,
    meta: dict[str, Any] | None = None,
) -> None:
    recs = [user(prompt, 20, isSidechain=True)]
    if replied:
        recs.append(assistant_text(f"synthetic handback from {name}", 21, isSidechain=True))
    else:
        recs += [assistant_tool(21), tool_result(22)]
    path = write_child(store, parent, name, recs)
    if meta is not None:
        path.with_suffix(".meta.json").write_text(json.dumps(meta), encoding="utf-8")


def unique_brief(name: str) -> str:
    return f"synthetic delegated brief for {name} with enough words to fingerprint"


@pytest.mark.skipif(CANNOT_DENY_WRITE, reason="needs a mode bit that denies the owner a write")
def test_prepare_unwritable_parent_exits_3_with_no_text(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(store, "main-a", thread("synthetic prompt wording sigma for exit3", [NEUTRAL]))
    plant_control(store)
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        code, payload, out = run_cli(capsys, prepare_args(store, locked / "run"))
    finally:
        locked.chmod(0o700)
    assert code == 3
    assert payload == IO_ERROR
    assert "synthetic" not in out
    assert CONTROL_TOKEN not in out
    assert not (locked / "run").exists()


def test_prepare_write_failure_exits_3_with_no_text(
    store: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> str:
        raise OSError("synthetic disk full detail")

    write_session(store, "main-a", thread("synthetic prompt wording tau for exit3", [NEUTRAL]))
    plant_control(store)
    monkeypatch.setattr(replies_prepare, "write_run", refuse)
    code, payload, out = run_cli(capsys, prepare_args(store, tmp_path / "run"))
    assert code == 3
    assert payload == IO_ERROR
    assert "synthetic" not in out
    assert CONTROL_TOKEN not in out


def test_tally_read_failure_exits_3_with_no_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("synthetic unreadable detail")

    monkeypatch.setattr(replies_tally, "load_run", refuse)
    argv = ["tally", "--run-dir", str(tmp_path / "run"), "--labels", str(tmp_path / "l.json")]
    code, payload, out = run_cli(capsys, argv)
    assert code == 3
    assert payload == IO_ERROR
    assert "synthetic" not in out


def test_first_follow_up_push_is_first_in_thread(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(store, "main-a", thread("synthetic prompt wording upsilon one", [PUSH]))
    followups = prepared_payload(capsys, store, tmp_path)["followups"]
    assert followups["typed"] == 1
    assert followups["flags"] == {"ownjob": 1}
    assert followups["pushes"] == {"first_in_thread": 1, "later": 0, "threads": 1}


def test_push_after_a_neutral_follow_up_still_counts_as_first_in_thread(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # replies_prepare.py:179 labels the first push of a thread, not the first follow-up.
    write_session(store, "main-a", thread("synthetic prompt wording phi two", [NEUTRAL, PUSH]))
    followups = prepared_payload(capsys, store, tmp_path)["followups"]
    assert followups["typed"] == 2
    assert followups["flags"] == {"ownjob": 1}
    assert followups["pushes"] == {"first_in_thread": 1, "later": 0, "threads": 1}


def test_second_and_third_pushes_in_one_thread_count_as_later(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recs = thread("synthetic prompt wording chi three", [PUSH, NUDGE, AUTHORITY])
    write_session(store, "main-a", recs)
    followups = prepared_payload(capsys, store, tmp_path)["followups"]
    assert followups["typed"] == 3
    assert followups["flags"] == {"generic_nudge": 1, "ownjob": 1, "prior_authority": 1}
    assert followups["pushes"] == {"first_in_thread": 1, "later": 2, "threads": 1}


def test_neutral_follow_up_is_typed_but_not_a_push(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(store, "main-a", thread("synthetic prompt wording psi four", [NEUTRAL]))
    followups = prepared_payload(capsys, store, tmp_path)["followups"]
    assert followups["typed"] == 1
    assert followups["flags"] == {}
    assert followups["pushes"] == {"first_in_thread": 0, "later": 0, "threads": 0}


def test_push_counts_aggregate_across_threads(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(store, "main-a", thread("synthetic prompt wording omega five", [PUSH]))
    write_session(store, "main-b", thread("synthetic prompt wording alpha six", [NEUTRAL]))
    write_session(
        store, "main-c", thread("synthetic prompt wording beta seven", [NUDGE, AUTHORITY])
    )
    followups = prepared_payload(capsys, store, tmp_path)["followups"]
    assert followups["typed"] == 4
    assert followups["pushes"] == {"first_in_thread": 2, "later": 1, "threads": 2}


def test_host_continue_turn_is_not_a_typed_follow_up(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recs = thread("synthetic prompt wording gamma eight", [])
    recs += [user(HOST_CONTINUE, 13), assistant_text("synthetic reply after host", 14)]
    write_session(store, "main-a", recs)
    payload = prepared_payload(capsys, store, tmp_path)
    assert payload["host_continues"] == 1
    assert payload["followups"]["typed"] == 0
    assert payload["followups"]["pushes"] == {"first_in_thread": 0, "later": 0, "threads": 0}


def test_handback_counts_cover_each_signal(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(
        store, "main-a", simple_session("synthetic parent prompt wording delta nine", ["ok"], 10)
    )
    write_session(
        store, "main-b", simple_session("synthetic parent prompt wording zeta ten", ["ok"], 30)
    )
    add_child(store, "main-a", "agent-noreply", unique_brief("noreply"), replied=False)
    add_child(
        store,
        "main-a",
        "agent-unfinished",
        unique_brief("unfinished"),
        meta={"agentType": "synthetic-type", "finished": False},
    )
    add_child(
        store,
        "main-a",
        "agent-nokey",
        unique_brief("nokey"),
        meta={"agentType": "synthetic-type"},
    )
    add_child(
        store,
        "main-a",
        "agent-done",
        unique_brief("done"),
        meta={"agentType": "synthetic-type", "finished": True},
    )
    add_child(
        store,
        "main-a",
        "agent-textual",
        unique_brief("textual"),
        meta={"agentType": "synthetic-type", "finished": "false"},
    )
    add_child(store, "main-a", "agent-twin-1", SHARED_BRIEF)
    add_child(store, "main-a", "agent-twin-2", SHARED_BRIEF)
    add_child(store, "main-b", "agent-twin-3", SHARED_BRIEF)
    payload = prepared_payload(capsys, store, tmp_path)
    assert payload["population"]["used"]["children"] == 8
    assert payload["handbacks"] == {
        "transcripts": 8,
        "no_reply": 1,
        "unfinished": 1,
        "finish_not_recorded": 2,
        "repeat_groups": 1,
        "repeat_transcripts": 2,
    }


def test_repeat_groups_need_the_same_parent_and_agent_type(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(
        store, "main-a", simple_session("synthetic parent prompt wording eta eleven", ["ok"], 10)
    )
    add_child(store, "main-a", "agent-one", SHARED_BRIEF, meta={"agentType": "type-one"})
    add_child(store, "main-a", "agent-two", SHARED_BRIEF, meta={"agentType": "type-two"})
    add_child(store, "main-a", "agent-three", SHARED_BRIEF, meta={"agentType": "type-two"})
    add_child(store, "main-a", "agent-four", SHARED_BRIEF, meta={"agentType": "type-two"})
    payload = prepared_payload(capsys, store, tmp_path)
    assert payload["handbacks"] == {
        "transcripts": 4,
        "no_reply": 0,
        "unfinished": 0,
        "finish_not_recorded": 4,
        "repeat_groups": 1,
        "repeat_transcripts": 3,
    }


def test_no_children_gives_zero_handbacks(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(
        store, "main-a", simple_session("synthetic parent prompt wording theta twelve", ["ok"], 10)
    )
    payload = prepared_payload(capsys, store, tmp_path)
    assert payload["handbacks"] == {
        "transcripts": 0,
        "no_reply": 0,
        "unfinished": 0,
        "finish_not_recorded": 0,
        "repeat_groups": 0,
        "repeat_transcripts": 0,
    }
