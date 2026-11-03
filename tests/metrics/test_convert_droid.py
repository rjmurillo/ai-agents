"""Tests for scripts/metrics/convert_droid.py with synthetic Droid records."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.failure_classifier import events_from_records, stop_feedback_count
from scripts.metrics import convert_droid as cd
from scripts.metrics.friction_calibration import inside_repository

TS = "2026-10-15T12:00:00.000Z"
SINCE = date(2026, 10, 3)


def _msg(role: str, content: object, ts: str | None = TS, **extra: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": "message",
        "id": "x",
        "message": {"role": role, "content": content, **extra},
    }
    if ts:
        record["timestamp"] = ts
    return record


def _use(use_id: str, name: str, tool_input: Any) -> dict[str, Any]:
    block = {"type": "tool_use", "id": use_id, "name": name, "input": tool_input}
    return _msg("assistant", [{"type": "thinking", "thinking": "hm"}, block])


def _res(use_id: str, content: Any, **flags: Any) -> dict[str, Any]:
    block = {"type": "tool_result", "tool_use_id": use_id, "content": content, **flags}
    return _msg("user", [block], visibility="llm_only")


def _human(text: str) -> dict[str, Any]:
    return _msg("user", [{"type": "text", "text": text}], userMessageSource="cli_tui")


def _start(sub: bool = False) -> dict[str, Any]:
    record: dict[str, Any] = {"type": "session_start", "id": "s"}
    if sub:
        record["callingSessionId"] = "parent"
    return record


def _convert(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], cd.Stats]:
    stats = cd.Stats()
    return cd.convert_records(records, stats), stats


def _write(path: Path, records: list[Any], raw: list[str] | None = None) -> Path:
    lines = [json.dumps(r) for r in records] + (raw or [])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_execute_maps_to_bash_with_command_only() -> None:
    inp = {"command": "make test", "riskLevel": "low", "summary": "s", "timeout": 5}
    out, stats = _convert([_use("t1", "Execute", inp)])
    assert out == [
        {
            "type": "assistant",
            "timestamp": TS,
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Bash",
                        "input": {"command": "make test"},
                    }
                ]
            },
        }
    ]
    assert stats.tool_calls == 1


def test_execute_without_string_command_gets_empty_command() -> None:
    out, _ = _convert([_use("t1", "Execute", None)])
    assert out[0]["message"]["content"][0]["input"] == {"command": ""}


def test_other_tools_keep_name_and_input_and_apply_patch_renamed() -> None:
    out, _ = _convert(
        [_use("t1", "Read", {"file_path": "/a"}), _use("t2", "ApplyPatch", {"input": "p"})]
    )
    blocks = [r["message"]["content"][0] for r in out]
    assert (blocks[0]["name"], blocks[0]["input"]) == ("Read", {"file_path": "/a"})
    assert blocks[1]["name"] == "apply_patch"


def test_success_and_failure_results_keep_original_text() -> None:
    text = "exit 1\n  trailing  "
    out, stats = _convert(
        [_res("a", "fine", is_error=False), _res("b", text, is_error=True), _res("c", "bare")]
    )
    blocks = [r["message"]["content"][0] for r in out]
    assert [b["is_error"] for b in blocks] == [False, True, False]
    assert blocks[1]["content"] == text
    assert all(r["toolUseResult"] == {} and r["timestamp"] == TS for r in out)
    assert stats.errored_results == 1


def test_list_result_content_is_passed_through() -> None:
    content = [{"type": "text", "text": "hi"}]
    out, _ = _convert([_res("a", content)])
    assert out[0]["message"]["content"][0]["content"] == content


def test_typed_prompt_is_human_and_injected_is_not() -> None:
    records = [
        _human("fix the bug"),
        _msg(
            "user",
            [{"type": "text", "text": "<system-reminder>x</system-reminder>"}],
            visibility="llm_only",
        ),
        _msg(
            "user",
            [{"type": "text", "text": "Background task completed"}],
            visibility="llm_only",
            userMessageSource="cli_tui",
        ),
        _msg("user", [{"type": "text", "text": "limit reached"}], visibility="user_only"),
        _msg("user", [{"type": "text", "text": "Reply ok"}]),
        _msg(
            "user",
            [{"type": "text", "text": "<system-reminder>agent</system-reminder>"}],
            userMessageSource="cli_tui",
        ),
    ]
    out, stats = _convert(records)
    assert out == [
        {
            "type": "user",
            "timestamp": TS,
            "promptSource": "typed",
            "message": {"content": "fix the bug"},
        }
    ]
    assert stats.human_turns == 1


def test_human_text_drops_injected_blocks_and_accepts_string_content() -> None:
    mixed = _msg(
        "user",
        [
            {"type": "text", "text": "<system-reminder>r</system-reminder>"},
            {"type": "text", "text": "do it"},
        ],
        userMessageSource="cli_tui",
    )
    plain = _msg("user", "as string", userMessageSource="cli_tui")
    out, _ = _convert([mixed, plain])
    assert [r["message"]["content"] for r in out] == ["do it", "as string"]


def test_assistant_prose_kept_thinking_dropped_and_empty_skipped() -> None:
    prose = _msg(
        "assistant", [{"type": "thinking", "thinking": "t"}, {"type": "text", "text": "done"}]
    )
    only_thinking = _msg("assistant", [{"type": "thinking", "thinking": "t"}])
    out, _ = _convert([prose, only_thinking])
    assert out == [
        {
            "type": "assistant",
            "timestamp": TS,
            "message": {"content": [{"type": "text", "text": "done"}]},
        }
    ]


def test_non_message_records_and_missing_timestamp_are_dropped() -> None:
    records: list[dict[str, Any]] = [
        {"type": "todo_state", "timestamp": TS, "todos": []},
        {"type": "agent_turn_outcome", "reason": "completed"},
        {"type": "compaction_state", "timestamp": TS},
        _use("t1", "Execute", {"command": "ls"}) | {"timestamp": ""},
        {"type": "message", "timestamp": TS, "message": "not a dict"},
    ]
    out, stats = _convert(records)
    assert out == []
    assert stats.skipped["no_timestamp"] == 1


def test_duplicate_and_malformed_tool_use_skipped() -> None:
    bad = _msg("assistant", [{"type": "tool_use", "id": 5, "name": "Read", "input": {}}])
    out, stats = _convert([_use("t1", "Read", {}), _use("t1", "Read", {}), bad])
    assert len(out) == 1
    assert stats.tool_calls == 1
    assert stats.skipped["bad_tool_use"] == 2


def test_result_block_without_id_is_ignored() -> None:
    out, _ = _convert([_msg("user", [{"type": "tool_result", "content": "x"}, "junk"])])
    assert out == []


def test_converted_records_read_by_classifier_adapter() -> None:
    records = [
        _use("t1", "Execute", {"command": "uv run pytest -q", "riskLevel": "low"}),
        _res("t1", "1 failed", is_error=True),
        _use("t2", "Edit", {"file_path": "/src/a.py"}),
        _res("t2", "ok", is_error=False),
        _human("thanks"),
    ]
    out, _ = _convert(records)
    events = events_from_records(out)
    assert [(e.tool, e.ok, e.error) for e in events] == [
        ("bash", False, "1 failed"),
        ("edit", True, "ok"),
    ]
    assert events[0].is_check
    assert events[1].target == "/src/a.py"
    assert stop_feedback_count(out) == 0


def test_hook_records_never_become_stop_feedback() -> None:
    hook = _msg("user", [], hookEventName="Stop", hookStatus="completed", hookResults=[])
    out, stats = _convert([hook])
    assert out == []
    assert stats.hook_blocks == 0


def test_is_subagent_and_first_day() -> None:
    assert cd.is_subagent([_start(sub=True)]) is True
    assert cd.is_subagent([_start()]) is False
    assert cd.first_day([{"type": "session_start"}, {"timestamp": TS}]) == date(2026, 10, 15)
    assert cd.first_day([{"timestamp": "bad"}, {"timestamp": 3}]) is None
    assert cd.parse_day("2026-10-15T23:30:00-05:00") == date(2026, 10, 16)
    assert cd.parse_day("2026-10-15T01:00:00") == date(2026, 10, 15)


def test_convert_file_window_subagent_empty_and_bad_lines(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    old = _write(
        tmp_path / "old.jsonl", [_use("a", "Read", {}) | {"timestamp": "2026-09-01T00:00:00Z"}]
    )
    sub = _write(tmp_path / "sub.jsonl", [_start(sub=True), _use("a", "Read", {})])
    empty = _write(tmp_path / "empty.jsonl", [_start(), _msg("assistant", [])])
    ok = _write(
        tmp_path / "ok.jsonl", [_start(), _use("a", "Read", {})], raw=["{not json", "[1]", ""]
    )
    written: set[str] = set()
    results = {
        p.stem: cd.convert_file(p, out_dir, SINCE, False, written) for p in (old, sub, empty, ok)
    }
    assert results["old"].skipped["window"] == 1
    assert results["sub"].skipped["subagent"] == 1
    assert results["empty"].skipped["empty"] == 1
    assert results["ok"].sessions == 1 and results["ok"].skipped["bad_line"] == 2
    assert sorted(p.name for p in out_dir.iterdir()) == ["ok.jsonl"]
    sub_stats = cd.convert_file(sub, out_dir, SINCE, True, written)
    assert sub_stats.sessions == 1 and sub_stats.tool_calls == 1


def test_duplicate_session_id_is_skipped(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    one = _write(tmp_path / "a" / "s.jsonl", [_use("a", "Read", {})])
    two = _write(tmp_path / "b" / "s.jsonl", [_use("b", "Read", {})])
    written: set[str] = set()
    assert cd.convert_file(one, out_dir, SINCE, False, written).sessions == 1
    assert cd.convert_file(two, out_dir, SINCE, False, written).skipped["duplicate_id"] == 1


def test_run_writes_private_files_and_totals(tmp_path: Path) -> None:
    src = tmp_path / "src" / "proj"
    src.mkdir(parents=True)
    _write(
        src / "s1.jsonl",
        [
            _start(),
            _human("go"),
            _use("a", "Execute", {"command": "ls"}),
            _res("a", "boom", is_error=True),
        ],
    )
    out_dir = tmp_path / "out"
    stats = cd.run(str(tmp_path / "src" / "*" / "*.jsonl"), out_dir, SINCE)
    assert (stats.files, stats.sessions, stats.tool_calls) == (1, 1, 1)
    assert (stats.errored_results, stats.human_turns, stats.hook_blocks) == (1, 1, 0)
    target = out_dir / "s1.jsonl"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    lines = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert [r["type"] for r in lines] == ["user", "assistant", "user"]
    assert all(r["timestamp"] == TS for r in lines)


def test_write_private_tightens_existing_file_mode(tmp_path: Path) -> None:
    path = tmp_path / "x.jsonl"
    path.write_text("old")
    os.chmod(path, 0o644)
    cd.write_private(path, [{"a": "é"}])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": "é"}


def test_summary_formats_skips() -> None:
    stats = cd.Stats(files=2)
    assert stats.summary().endswith("skipped=0")
    stats.skipped["window"] = 3
    assert stats.summary().endswith("skipped=window:3")


def test_main_refuses_out_dir_inside_git_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    out_dir = tmp_path / "out"
    code = cd.main(
        [
            "--src-glob",
            str(tmp_path / "*.jsonl"),
            "--out-dir",
            str(out_dir),
            "--since",
            "2026-10-03",
        ]
    )
    assert code == cd.EXIT_CONFIG
    assert "inside a git repository" in capsys.readouterr().err
    assert not out_dir.exists()
    assert inside_repository(out_dir)


def test_main_prints_counts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(tmp_path / "s.jsonl", [_start(), _use("a", "Read", {})])
    out_dir = tmp_path / "private" / "out"
    argv = [
        "--src-glob",
        str(tmp_path / "*.jsonl"),
        "--out-dir",
        str(out_dir),
        "--since",
        "2026-10-03",
    ]
    # tmp_path lives outside a repo on CI and locally; skip when it does not.
    if inside_repository(out_dir):
        pytest.skip("tmp_path is inside a git repository")
    assert cd.main(argv) == cd.EXIT_OK
    assert "sessions=1 tool_calls=1" in capsys.readouterr().out


def test_bad_since_date_exits_with_usage_error() -> None:
    with pytest.raises(SystemExit) as info:
        cd.build_parser().parse_args(["--src-glob", "x", "--out-dir", "y", "--since", "10/03"])
    assert info.value.code == 2


@pytest.mark.parametrize("hostile", [".hidden", "..", "-lead", "a b"])
def test_hostile_session_stem_is_skipped_and_counted(tmp_path: Path, hostile: str) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    src = _write(tmp_path / f"{hostile}.jsonl", [_use("a", "Read", {})])
    stats = cd.convert_file(src, out_dir, SINCE, False, set())
    assert (stats.sessions, stats.skipped["unsafe_id"]) == (0, 1)
    assert list(out_dir.iterdir()) == []


def test_planted_symlink_at_output_is_not_written_through(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("keep", encoding="utf-8")
    (out_dir / "s.jsonl").symlink_to(victim)
    src = _write(tmp_path / "s.jsonl", [_use("a", "Read", {})])
    assert cd.convert_file(src, out_dir, SINCE, False, set()).sessions == 1
    assert victim.read_text(encoding="utf-8") == "keep"
    target = out_dir / "s.jsonl"
    assert not target.is_symlink()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_run_creates_out_dir_0700_and_tightens_existing(tmp_path: Path) -> None:
    pattern = str(tmp_path / "none" / "*" / "*.jsonl")
    fresh = tmp_path / "fresh"
    cd.run(pattern, fresh, SINCE)
    assert stat.S_IMODE(fresh.stat().st_mode) == 0o700
    loose = tmp_path / "loose"
    loose.mkdir()
    loose.chmod(0o755)
    cd.run(pattern, loose, SINCE)
    assert stat.S_IMODE(loose.stat().st_mode) == 0o700


def test_lone_surrogate_in_record_is_escaped_not_a_write_crash(tmp_path: Path) -> None:
    path = tmp_path / "x.jsonl"
    cd.write_private(path, [{"a": "x\ud800y"}])
    assert path.read_bytes().isascii()
