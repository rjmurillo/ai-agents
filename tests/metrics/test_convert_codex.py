"""Tests for scripts/metrics/convert_codex.py using synthetic Codex records."""

from __future__ import annotations

import json
import stat
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.failure_classifier import events_from_records
from scripts.metrics import convert_codex as cc

TS = "2026-10-05T03:50:32.168Z"
HOOK_TS = "2026-10-05T03:51:00.000Z"


def _line(kind: str, payload: dict[str, Any], ts: str = TS) -> str:
    return json.dumps({"timestamp": ts, "type": kind, "payload": payload})


def _meta(**extra: Any) -> str:
    return _line("session_meta", {"id": "sess-1", "source": "exec", **extra})


def _item(item: dict[str, Any], ts: str = TS) -> str:
    return _line("event_msg", {"type": "item_completed", "item": item}, ts)


def _cmd(item_id: str, script: str, exit_code: int, out: str, status: str = "completed") -> str:
    return _item(
        {
            "type": "CommandExecution",
            "id": item_id,
            "command": ["/usr/bin/zsh", "-lc", script],
            "aggregated_output": out,
            "exit_code": exit_code,
            "status": status,
        }
    )


def _convert(*lines: str) -> tuple[str | None, str, list[dict[str, Any]]]:
    return cc.convert_lines(lines)


def _blocks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [b for r in records for b in r["message"]["content"] if isinstance(b, dict)]


def test_shell_success_maps_to_bash_pair() -> None:
    _, sid, recs = _convert(_meta(), _cmd("c1", "git status", 0, "clean\n"))
    use, result = _blocks(recs)
    assert sid == "sess-1"
    assert use == {
        "type": "tool_use",
        "id": "c1",
        "name": "Bash",
        "input": {"command": "git status"},
    }
    assert result["tool_use_id"] == "c1"
    assert result["content"] == "clean\n"
    assert result["is_error"] is False
    assert "toolUseResult" in recs[1]


def test_shell_failure_flags_nonzero_exit_and_keeps_text() -> None:
    _, _, recs = _convert(_meta(), _cmd("c2", "gh api x", 1, "gh: denied (HTTP 403)\n"))
    result = _blocks(recs)[1]
    assert result["is_error"] is True
    assert result["content"] == "gh: denied (HTTP 403)\n"


def test_failed_status_with_zero_exit_is_error() -> None:
    _, _, recs = _convert(_meta(), _cmd("c3", "x", 0, "", status="failed"))
    assert _blocks(recs)[1]["is_error"] is True


def test_non_shell_argv_is_joined() -> None:
    assert cc._command_text(["ls", "-la", "my dir"]) == "ls -la 'my dir'"
    assert cc._command_text("echo hi") == "echo hi"
    assert cc._command_text(None) == ""


def test_mcp_success_and_error() -> None:
    ok = {
        "type": "McpToolCall",
        "id": "m1",
        "server": "ctx",
        "tool": "run",
        "arguments": {"a": 1},
        "status": "completed",
        "result": {"content": [{"type": "text", "text": "hello"}]},
    }
    bad = {**ok, "id": "m2", "status": "failed", "result": None, "error": {"message": "closed"}}
    _, _, recs = _convert(_meta(), _item(ok), _item(bad))
    uses = [b for b in _blocks(recs) if b["type"] == "tool_use"]
    results = [b for b in _blocks(recs) if b["type"] == "tool_result"]
    assert uses[0]["name"] == "mcp__ctx__run"
    assert [r["content"] for r in results] == ["hello", "closed"]
    assert [r["is_error"] for r in results] == [False, True]


def test_file_change_maps_to_apply_patch_with_target() -> None:
    item = {
        "type": "FileChange",
        "id": "f1",
        "changes": {"/a/b.py": {}},
        "status": "completed",
        "stdout": "Success.",
    }
    _, _, recs = _convert(_meta(), _item(item))
    assert _blocks(recs)[0]["name"] == "apply_patch"
    events = events_from_records(recs)
    assert events[0].target == "/a/b.py"


def test_function_call_pairs_by_call_id() -> None:
    call = _line(
        "response_item",
        {"type": "function_call", "name": "wait", "call_id": "k1", "arguments": '{"cell_id": "1"}'},
    )
    out = _line(
        "response_item", {"type": "function_call_output", "call_id": "k1", "output": "done"}
    )
    orphan = _line(
        "response_item", {"type": "function_call_output", "call_id": "zz", "output": "x"}
    )
    _, _, recs = _convert(_meta(), call, out, orphan)
    use, result = _blocks(recs)
    assert use["input"] == {"cell_id": "1"}
    assert result["content"] == "done"
    assert len(recs) == 2


def test_exec_wrapper_only_emitted_on_failure() -> None:
    def pair(call_id: str, text: str) -> list[str]:
        return [
            _line(
                "response_item",
                {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": call_id,
                    "input": "tools.x()",
                },
            ),
            _line(
                "response_item",
                {
                    "type": "custom_tool_call_output",
                    "call_id": call_id,
                    "output": [{"type": "input_text", "text": text}],
                },
            ),
        ]

    _, _, recs = _convert(
        _meta(), *pair("w1", "Script completed\nOutput:\n"), *pair("w2", "Script failed\nboom")
    )
    blocks = _blocks(recs)
    assert [b.get("id") or b.get("tool_use_id") for b in blocks] == ["w2", "w2"]
    assert blocks[1]["is_error"] is True


def test_human_prompt_versus_injected_context() -> None:
    def user(text: str) -> str:
        return _item(
            {"type": "UserMessage", "id": "u", "content": [{"type": "text", "text": text}]}
        )

    _, _, recs = _convert(
        _meta(),
        user("fix the bug"),
        user("<environment_context>x</environment_context>"),
        user("# AGENTS.md instructions for /repo"),
        user("   "),
    )
    assert len(recs) == 1
    assert recs[0]["promptSource"] == "typed"
    assert recs[0]["message"]["content"] == "fix the bug"
    assert "toolUseResult" not in recs[0]


def test_human_falls_back_to_event_then_response_item() -> None:
    event = _line("event_msg", {"type": "user_message", "message": "legacy prompt"})
    resp = _line(
        "response_item",
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "resp prompt"}],
        },
    )
    injected = _line(
        "response_item",
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<x>"}]},
    )
    _, _, with_event = _convert(_meta(), event, resp)
    _, _, only_resp = _convert(_meta(), resp, injected)
    assert [r["message"]["content"] for r in with_event] == ["legacy prompt"]
    assert [r["message"]["content"] for r in only_resp] == ["resp prompt"]


def test_agent_text_record() -> None:
    msg = _item({"type": "AgentMessage", "id": "a", "content": [{"type": "Text", "text": "done"}]})
    _, _, recs = _convert(_meta(), msg)
    assert recs[0]["message"]["content"] == [{"type": "text", "text": "done"}]


def test_stop_hook_prompt_maps_to_feedback_and_other_hooks_do_not() -> None:
    def hook(run: str, text: str) -> str:
        return _item(
            {"type": "HookPrompt", "id": "h", "fragments": [{"text": text, "hookRunId": run}]},
            HOOK_TS,
        )

    _, _, recs = _convert(
        _meta(), hook("stop:1:/h.json", "run the tests"), hook("pre:1:/h.json", "ignored")
    )
    assert len(recs) == 1
    assert recs[0]["message"]["content"] == "Stop hook feedback:\nrun the tests"
    assert recs[0]["timestamp"] == HOOK_TS
    assert cc._count(recs)["hook_blocks"] == 1


@pytest.mark.parametrize(
    "extra",
    [
        {"thread_source": "subagent"},
        {"source": {"subagent": {"thread_spawn": {}}}},
        {"parent_thread_id": "p"},
        {"forked_from_id": "f"},
    ],
)
def test_subagent_and_fork_sessions_are_skipped(extra: dict[str, Any]) -> None:
    reason, _, recs = _convert(_meta(**extra), _cmd("c", "x", 0, ""))
    assert reason == "subagent_or_fork"
    assert recs == []


def test_every_record_carries_timestamp() -> None:
    _, _, recs = _convert(
        _meta(),
        _cmd("c", "x", 0, "o"),
        _item({"type": "AgentMessage", "content": [{"text": "t"}]}, HOOK_TS),
    )
    assert [r["timestamp"] for r in recs] == [TS, TS, HOOK_TS]


def test_records_without_timestamp_or_bad_json_are_ignored() -> None:
    bad = json.dumps({"type": "event_msg", "payload": {"type": "item_completed"}})
    _, _, recs = _convert("not json", "[]", bad, _meta())
    assert recs == []


def test_events_from_records_reads_converted_output() -> None:
    _, _, recs = _convert(
        _meta(),
        _cmd("c1", "ls", 0, "ok"),
        _cmd("c2", "gh x", 1, "permission denied"),
    )
    events = events_from_records(recs)
    assert [e.tool for e in events] == ["bash", "bash"]
    assert [e.ok for e in events] == [True, False]
    assert events[1].error == "permission denied"


def _write_src(path: Path, *lines: str) -> str:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_convert_files_counts_modes_and_since(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    keep = _write_src(src / "rollout-a.jsonl", _meta(), _cmd("c", "x", 1, "e"))
    sub = _write_src(src / "rollout-b.jsonl", _meta(thread_source="subagent"))
    old = _write_src(
        src / "rollout-c.jsonl",
        _meta(),
        _item({"type": "AgentMessage", "content": [{"text": "t"}]}, "2026-01-01T00:00:00Z"),
    )
    out = tmp_path / "out"
    out.mkdir()
    totals = cc.convert_files([keep, sub, old], out, date(2026, 10, 1))
    assert (totals["files"], totals["sessions"], totals["skipped"]) == (3, 1, 2)
    assert (totals["tool_calls"], totals["errored"]) == (1, 1)
    target = out / "sess-1.jsonl"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert len(target.read_text().splitlines()) == 2


def test_duplicate_session_ids_get_distinct_files(tmp_path: Path) -> None:
    a = _write_src(tmp_path / "rollout-a.jsonl", _meta(), _cmd("c", "x", 0, ""))
    b = _write_src(tmp_path / "rollout-b.jsonl", _meta(), _cmd("c", "x", 0, ""))
    out = tmp_path / "out"
    out.mkdir()
    cc.convert_files([a, b], out, date(2026, 1, 1))
    assert sorted(p.name for p in out.iterdir()) == ["sess-1-2.jsonl", "sess-1.jsonl"]


def test_main_refuses_out_dir_inside_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    code = cc.main(["--src-glob", "x", "--out-dir", str(repo / "out"), "--since", "2026-10-01"])
    assert code == 2
    assert "inside a git repository" in capsys.readouterr().err


def test_main_rejects_bad_since(tmp_path: Path) -> None:
    assert cc.main(["--src-glob", "x", "--out-dir", str(tmp_path), "--since", "nope"]) == 2


def test_main_prints_counts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_src(tmp_path / "rollout-a.jsonl", _meta(), _cmd("c", "x", 1, "e"))
    out = tmp_path / "out"
    code = cc.main(
        [
            "--src-glob",
            str(tmp_path / "rollout-*.jsonl"),
            "--out-dir",
            str(out),
            "--since",
            "2026-10-01",
        ]
    )
    printed = capsys.readouterr().out
    assert code == 0
    assert "sessions=1" in printed
    assert "errored=1" in printed


@pytest.mark.parametrize("hostile", ["../x", "a/b", "", ".hidden"])
def test_hostile_session_id_falls_back_to_the_safe_file_stem(tmp_path: Path, hostile: str) -> None:
    src = _write_src(tmp_path / "rollout-a.jsonl", _meta(id=hostile), _cmd("c", "x", 0, ""))
    out = tmp_path / "out"
    out.mkdir()
    totals = cc.convert_files([src], out, date(2026, 1, 1))
    assert totals["sessions"] == 1 and totals.get("skipped_unsafe_id", 0) == 0
    assert [p.name for p in out.iterdir()] == ["rollout-a.jsonl"]
    assert not (tmp_path / "x.jsonl").exists()


def test_unsafe_id_and_unsafe_stem_is_skipped(tmp_path: Path) -> None:
    src = _write_src(tmp_path / "rollout a.jsonl", _meta(id="../x"), _cmd("c", "x", 0, ""))
    out = tmp_path / "out"
    out.mkdir()
    totals = cc.convert_files([src], out, date(2026, 1, 1))
    assert (totals["sessions"], totals["skipped_unsafe_id"]) == (0, 1)
    assert list(out.iterdir()) == []


def test_planted_symlink_at_output_is_not_written_through(tmp_path: Path) -> None:
    src = _write_src(tmp_path / "rollout-a.jsonl", _meta(), _cmd("c", "x", 0, ""))
    out = tmp_path / "out"
    out.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("keep", encoding="utf-8")
    (out / "sess-1.jsonl").symlink_to(victim)
    cc.convert_files([src], out, date(2026, 1, 1))
    assert victim.read_text(encoding="utf-8") == "keep"
    target = out / "sess-1.jsonl"
    assert not target.is_symlink()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_missing_session_id_falls_back_to_the_file_stem(tmp_path: Path) -> None:
    from scripts.metrics import convert_codex as cc

    rollout = tmp_path / "rollout-2026-10-10T10-00-00-abc.jsonl"
    rollout.write_text(
        json.dumps(
            {
                "type": "event_msg",
                "timestamp": "2026-10-10T10:00:00Z",
                "payload": {"type": "user_message", "message": "fix the bug"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    out.mkdir()
    totals = cc.convert_files([str(rollout)], out, date(2026, 10, 1))
    assert totals.get("skipped_unsafe_id", 0) == 0
    assert (out / f"{rollout.stem}.jsonl").exists()
