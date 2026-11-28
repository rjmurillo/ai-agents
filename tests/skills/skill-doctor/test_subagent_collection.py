"""Subagent sessions are collected by default and stay distinguishable from top-level ones.

Every journal is synthetic and lives under pytest's tmp_path.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from contextlib import closing

import pytest
from session_test_helpers import run_collector, write_jsonl
from test_repository_scope import add_worktree, make_clone

STAMP = "2026-10-01T10:00:00Z"
UPSTREAM = "https://example.invalid/acme/widgets.git"


def claude_records(session_id, cwd, *, agent_id=None, branch=None):
    base = {"sessionId": session_id, "cwd": cwd, "timestamp": STAMP}
    if branch:
        base["gitBranch"] = branch
    if agent_id:
        base.update({"agentId": agent_id, "isSidechain": True})
    return [
        {**base, "type": "user", "message": {"role": "user", "content": "Investigate the parser"}},
        {
            **base,
            "type": "assistant",
            "message": {
                "id": f"msg-{session_id}-{agent_id}",
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Looking."},
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}},
                ],
            },
        },
    ]


def write_claude(
    home, session_id, cwd, *, child_cwd=None, project="-repo", child=True, branch=None
):
    """Write a parent journal and, when ``child`` is set, one subagent journal beside it."""
    root = home / "projects" / project
    write_jsonl(root / f"{session_id}.jsonl", claude_records(session_id, str(cwd), branch=branch))
    if child:
        write_jsonl(
            root / session_id / "subagents" / "agent-x.jsonl",
            claude_records(session_id, str(child_cwd or cwd), agent_id="x", branch=branch),
        )


def collect(tmp_path, *args, harness="claude"):
    result = run_collector(
        tmp_path,
        tmp_path / "copilot-home",
        "--harness",
        harness,
        "--min-idle-minutes",
        "0",
        *args,
    )
    assert result.returncode == 0, result.stderr
    inventory = json.loads((tmp_path / "report" / "inventory.json").read_text(encoding="utf-8"))
    return inventory, result


def by_thread(inventory):
    return {session["thread"]: session for session in inventory["sessions"]}


@pytest.fixture
def claude_home(tmp_path):
    home = tmp_path / "claude-home"
    write_claude(home, "parent", tmp_path / "repo")
    return home


def test_default_collection_includes_subagent_session(tmp_path, claude_home):
    inventory, _ = collect(tmp_path, "--claude-home", str(claude_home), "--all-conversations")
    assert inventory["stats"]["sessions_considered"] == 2
    sessions = by_thread(inventory)
    assert set(sessions) == {"top_level", "subagent"}
    assert sessions["subagent"]["meta"]["thread_source"] == "subagent"
    assert sessions["top_level"]["meta"]["thread_source"] is None


def test_inventory_splits_counts_by_thread(tmp_path, claude_home):
    inventory, result = collect(tmp_path, "--claude-home", str(claude_home), "--all-conversations")
    per_thread = inventory["stats"]["per_thread"]
    assert per_thread == {
        "top_level": {"scoreable": 1, "sampled": 1},
        "subagent": {"scoreable": 1, "sampled": 1},
    }
    claude = inventory["stats"]["per_harness"]["claude"]
    assert claude["scoreable_subagent"] == 1
    assert claude["sampled_subagent"] == 1
    assert "subagent" in result.stdout


def test_no_include_subagents_excludes_child(tmp_path, claude_home):
    inventory, _ = collect(
        tmp_path,
        "--claude-home",
        str(claude_home),
        "--all-conversations",
        "--no-include-subagents",
    )
    assert [s["thread"] for s in inventory["sessions"]] == ["top_level"]
    assert inventory["stats"]["per_thread"]["subagent"] == {"scoreable": 0, "sampled": 0}


def test_explicit_include_flag_still_includes_child(tmp_path, claude_home):
    inventory, _ = collect(
        tmp_path,
        "--claude-home",
        str(claude_home),
        "--all-conversations",
        "--include-subagents",
    )
    assert {s["thread"] for s in inventory["sessions"]} == {"top_level", "subagent"}


def test_child_in_scope_with_parent_out_of_scope_is_kept(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "claude-home"
    write_claude(home, "parent", tmp_path / "elsewhere", child_cwd=repo)
    inventory, _ = collect(tmp_path, "--claude-home", str(home), "--repo", str(repo))
    assert [s["thread"] for s in inventory["sessions"]] == ["subagent"]


def test_child_out_of_scope_with_parent_in_scope_is_dropped(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    home = tmp_path / "claude-home"
    write_claude(home, "parent", repo, child_cwd=tmp_path / "elsewhere")
    inventory, _ = collect(tmp_path, "--claude-home", str(home), "--repo", str(repo))
    assert [s["thread"] for s in inventory["sessions"]] == ["top_level"]


def test_child_in_registered_linked_worktree_is_kept(tmp_path):
    main = make_clone(tmp_path / "clones" / "widgets", UPSTREAM)
    tree = add_worktree(main, tmp_path / "trees" / "widgets" / "feature-a", "feature-a")
    home = tmp_path / "claude-home"
    write_claude(home, "parent", tmp_path / "elsewhere", child_cwd=tree)
    inventory, _ = collect(tmp_path, "--claude-home", str(home), "--repo", str(main))
    assert [s["thread"] for s in inventory["sessions"]] == ["subagent"]


def test_child_in_removed_worktree_stays_in_scope_by_its_branch(tmp_path):
    main = make_clone(tmp_path / "clones" / "widgets", UPSTREAM)
    tree = add_worktree(main, tmp_path / "trees" / "widgets" / "gone", "gone-branch")
    home = tmp_path / "claude-home"
    write_claude(home, "parent", tree, branch="gone-branch")
    shutil.rmtree(tree)
    inventory, _ = collect(tmp_path, "--claude-home", str(home), "--repo", str(main))
    assert sorted(s["thread"] for s in inventory["sessions"]) == ["subagent", "top_level"]
    assert inventory["scope_resolution"]["removed_checkout_sessions"] == 2


def test_child_in_removed_worktree_without_a_recorded_branch_falls_out(tmp_path):
    main = make_clone(tmp_path / "clones" / "widgets", UPSTREAM)
    tree = add_worktree(main, tmp_path / "trees" / "widgets" / "gone", "gone-branch")
    home = tmp_path / "claude-home"
    write_claude(home, "parent", tmp_path / "elsewhere", child_cwd=tree)
    shutil.rmtree(tree)
    inventory, _ = collect(tmp_path, "--claude-home", str(home), "--repo", str(main))
    assert inventory["sessions"] == []


def codex_rollout(session_id, **payload):
    base = {"timestamp": STAMP}
    meta = {"id": session_id, "cwd": "/work/repo", "timestamp": STAMP, **payload}
    return [
        {**base, "type": "session_meta", "payload": meta},
        {**base, "type": "event_msg", "payload": {"type": "user_message", "message": "go"}},
        {**base, "type": "event_msg", "payload": {"type": "agent_message", "message": "ok"}},
        {
            **base,
            "type": "response_item",
            "payload": {"type": "function_call", "name": "shell", "arguments": "{}"},
        },
    ]


def test_codex_source_dict_child_is_tagged_subagent(tmp_path):
    home = tmp_path / "codex-home"
    day = home / "sessions" / "2026" / "10" / "01"
    write_jsonl(
        day / "rollout-child.jsonl", codex_rollout("child", source={"subagent": {"parent": "p"}})
    )
    write_jsonl(day / "rollout-top.jsonl", codex_rollout("top"))
    inventory, _ = collect(
        tmp_path, "--codex-home", str(home), "--all-conversations", harness="codex"
    )
    sessions = {s["meta"]["id"]: s for s in inventory["sessions"]}
    assert sessions["child"]["thread"] == "subagent"
    assert sessions["child"]["meta"]["thread_source"] == "subagent"
    assert sessions["top"]["thread"] == "top_level"
    excluded, _ = collect(
        tmp_path,
        "--codex-home",
        str(home),
        "--all-conversations",
        "--no-include-subagents",
        harness="codex",
    )
    assert [s["meta"]["id"] for s in excluded["sessions"]] == ["top"]


def make_hermes(home):
    home.mkdir(parents=True)
    with closing(sqlite3.connect(home / "state.db")) as conn:
        conn.execute(
            """CREATE TABLE sessions (
                id TEXT, source TEXT, cwd TEXT, title TEXT, display_name TEXT,
                parent_session_id TEXT, started_at REAL, last_activity_at REAL, ended_at REAL)"""
        )
        conn.execute(
            """CREATE TABLE messages (
                session_id TEXT, role TEXT, content TEXT, tool_calls TEXT, timestamp REAL)"""
        )
        base = time.time() - 3600
        calls = json.dumps([{"function": {"name": "terminal", "arguments": "ls"}}])
        for sid, parent in (("top", None), ("kid", "top")):
            conn.execute(
                "INSERT INTO sessions VALUES (?, 'cli', '/work/repo', 't', 'd', ?, ?, ?, ?)",
                (sid, parent, base, base + 60, base + 60),
            )
            conn.execute("INSERT INTO messages VALUES (?, 'user', 'go', NULL, ?)", (sid, base))
            conn.execute(
                "INSERT INTO messages VALUES (?, 'assistant', 'ok', ?, ?)", (sid, calls, base + 1)
            )
        conn.commit()


def test_hermes_child_is_tagged_subagent_and_keeps_parent_id(tmp_path):
    home = tmp_path / "hermes-home"
    make_hermes(home)
    inventory, _ = collect(
        tmp_path, "--hermes-home", str(home), "--all-conversations", harness="hermes"
    )
    sessions = {s["meta"]["id"]: s for s in inventory["sessions"]}
    assert sessions["kid"]["thread"] == "subagent"
    assert sessions["kid"]["meta"]["thread_source"] == "subagent"
    assert sessions["kid"]["meta"]["parent_session_id"] == "top"
    assert sessions["top"]["thread"] == "top_level"


def write_copilot(home):
    path = home / "session-state" / "s1" / "events.jsonl"

    def row(kind, data, **extra):
        return {"type": kind, "timestamp": STAMP, "data": data, **extra}

    write_jsonl(
        path,
        [
            row("session.start", {"sessionId": "s1", "context": {"cwd": "/work/repo"}}),
            row("user.message", {"content": "go"}),
            row("assistant.message", {"content": "parent turn"}),
            row("tool.execution_start", {"toolName": "bash", "arguments": {}, "toolCallId": "p1"}),
            row("assistant.message", {"content": "child turn"}, agentId="sub-1"),
            row(
                "tool.execution_start",
                {"toolName": "view", "arguments": {}, "toolCallId": "c1"},
                agentId="sub-1",
            ),
        ],
    )


@pytest.mark.parametrize(
    ("extra", "folded"),
    [((), False), (("--include-subagents",), True), (("--no-include-subagents",), False)],
)
def test_copilot_folds_inline_child_events_only_when_asked(tmp_path, extra, folded):
    write_copilot(tmp_path / "copilot-home")
    inventory, _ = collect(tmp_path, "--all-conversations", *extra, harness="copilot")
    stats = inventory["sessions"][0]["stats"]
    assert inventory["sessions"][0]["thread"] == "top_level"
    assert stats["assistant_turns"] == (2 if folded else 1)
    assert stats["tool_calls"] == (2 if folded else 1)


def test_top_level_gap_notice_names_the_gap_and_stays_quiet_otherwise():
    from session_threads import top_level_gap_notice

    gap = {
        "top_level": {"scoreable": 3, "sampled": 0},
        "subagent": {"scoreable": 2, "sampled": 2},
    }
    assert "no top-level sessions although 3" in top_level_gap_notice(gap)
    covered = {**gap, "top_level": {"scoreable": 3, "sampled": 1}}
    assert top_level_gap_notice(covered) is None
    none_scoreable = {**gap, "top_level": {"scoreable": 0, "sampled": 0}}
    assert top_level_gap_notice(none_scoreable) is None
