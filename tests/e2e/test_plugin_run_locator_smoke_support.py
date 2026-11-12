#!/usr/bin/env python3
"""Unit tests of the ADR-121 locator smoke helpers (no CLI, no model call)."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "build" / "scripts"))

import plugin_run_locator_smoke_support as support
from plugin_run_launcher import render_locator
from plugin_run_locator_smoke_support import (
    ATTEMPTS,
    LEGACY_COMMAND,
    LEGACY_SKILL,
    MARKER,
    MODEL,
    PLUGIN_NAME,
    POSITIVE_SKILL,
    RESOLVER_SOURCE,
    STUB_SOURCE,
    TARGET_ARG,
    TARGET_REL,
    Observation,
    build_plugin,
    claude_command,
    gate_skip_reason,
    observe,
    parse_stream,
    run_with_retry,
    smoke_env,
)


def _stream(*events: Mapping[str, object]) -> str:
    return "\n".join(json.dumps(event) for event in events)


def _bash_use(command: str) -> dict[str, object]:
    block = {"type": "tool_use", "name": "Bash", "input": {"command": command}}
    return {"type": "assistant", "message": {"content": [block]}}


def _tool_result(content: object) -> dict[str, object]:
    block = {"type": "tool_result", "content": content}
    return {"type": "user", "message": {"content": [block]}}


def _observation(stdout: str) -> Observation:
    return observe(subprocess.CompletedProcess([], 0, stdout, ""))


def test_gate_is_open_only_with_both_flags_and_the_cli() -> None:
    both = {"RUN_CLI_E2E": "1", "RUN_CLI_MODEL_E2E": "1"}
    assert gate_skip_reason(both, "/usr/bin/claude") is None


@pytest.mark.parametrize(
    ("environ", "claude_path", "named"),
    [
        ({}, "/usr/bin/claude", "RUN_CLI_E2E=1"),
        ({"RUN_CLI_E2E": "1"}, "/usr/bin/claude", "RUN_CLI_MODEL_E2E=1"),
        ({"RUN_CLI_MODEL_E2E": "1"}, "/usr/bin/claude", "RUN_CLI_E2E=1"),
        ({"RUN_CLI_E2E": "1", "RUN_CLI_MODEL_E2E": "1"}, None, "claude CLI on PATH"),
        ({"RUN_CLI_E2E": "0", "RUN_CLI_MODEL_E2E": "1"}, "/usr/bin/claude", "RUN_CLI_E2E=1"),
    ],
)
def test_gate_names_every_missing_piece(
    environ: dict[str, str], claude_path: str | None, named: str
) -> None:
    reason = gate_skip_reason(environ, claude_path)
    assert reason is not None
    assert "SKIPPED" in reason
    assert named in reason


def test_gate_lists_all_missing_pieces_together() -> None:
    reason = gate_skip_reason({}, None)
    assert reason is not None
    for named in ("RUN_CLI_E2E=1", "RUN_CLI_MODEL_E2E=1", "claude CLI on PATH"):
        assert named in reason


def test_parse_stream_reads_bash_commands_and_results() -> None:
    stdout = _stream(
        {"type": "system"},
        _bash_use("echo hi"),
        _tool_result("hi"),
        _tool_result([{"type": "text", "text": "listed"}]),
    )
    commands, results = parse_stream(stdout)
    assert commands == ("echo hi",)
    assert results == ("hi", "listed")


def test_parse_stream_skips_non_bash_tools_junk_lines_and_odd_shapes() -> None:
    other = {"type": "tool_use", "name": "Read", "input": {"file_path": "x"}}
    stdout = "\n".join(
        [
            "not json",
            "[1, 2]",
            _stream({"type": "assistant", "message": {"content": [other]}}),
            _stream({"type": "assistant", "message": {"content": "plain text"}}),
            _stream({"type": "assistant", "message": "odd"}),
            _stream(_tool_result(None)),
        ]
    )
    assert parse_stream(stdout) == ((), ("",))


def test_parse_stream_on_empty_output() -> None:
    assert parse_stream("") == ((), ())


def test_marker_ran_needs_the_marker_and_the_argument() -> None:
    good = json.dumps({"marker": MARKER, "argv": [TARGET_ARG]})
    wrong_arg = json.dumps({"marker": MARKER, "argv": []})
    assert _observation(_stream(_tool_result(f"noise\n{good}"))).marker_ran()
    assert not _observation(_stream(_tool_result(wrong_arg))).marker_ran()
    assert not _observation(_stream(_tool_result("no json here"))).marker_ran()


def test_marker_in_model_prose_alone_is_not_a_run() -> None:
    prose = {"type": "assistant", "message": {"content": [{"type": "text", "text": MARKER}]}}
    seen = _observation(_stream(prose))
    assert seen.marker_anywhere()
    assert not seen.marker_ran()


def test_build_plugin_writes_the_plugin_the_run_needs(tmp_path: Path) -> None:
    plugin = build_plugin(tmp_path)

    manifest = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    assert manifest["name"] == PLUGIN_NAME
    assert (plugin / "lib" / "ptk_run.py").read_bytes() == RESOLVER_SOURCE.read_bytes()
    assert (plugin / TARGET_REL).read_text("utf-8") == STUB_SOURCE
    positive = (plugin / "skills" / POSITIVE_SKILL / "SKILL.md").read_text("utf-8")
    legacy = (plugin / "skills" / LEGACY_SKILL / "SKILL.md").read_text("utf-8")
    assert render_locator(TARGET_REL, TARGET_ARG) in positive
    assert "${CLAUDE_PLUGIN_ROOT}" in positive
    assert LEGACY_COMMAND in legacy


def test_skill_text_never_leaks_the_marker(tmp_path: Path) -> None:
    plugin = build_plugin(tmp_path)
    for skill in (POSITIVE_SKILL, LEGACY_SKILL):
        assert MARKER not in (plugin / "skills" / skill / "SKILL.md").read_text("utf-8")


def test_stub_prints_the_marker_line_for_its_arguments(tmp_path: Path) -> None:
    plugin = build_plugin(tmp_path)
    run = subprocess.run(
        [sys.executable, str(plugin / TARGET_REL), TARGET_ARG],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert run.returncode == 0
    assert json.loads(run.stdout) == {"marker": MARKER, "argv": [TARGET_ARG]}


def test_smoke_env_strips_plugin_root_and_data_and_keeps_extras(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/x")
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", "/y")
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", "/z")
    monkeypatch.setenv("KEEP_ME", "1")

    bare = smoke_env()
    assert not {"CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA", "COPILOT_PLUGIN_ROOT"} & set(bare)
    assert bare["KEEP_ME"] == "1"
    assert smoke_env({"CLAUDE_PLUGIN_ROOT": "/foreign"})["CLAUDE_PLUGIN_ROOT"] == "/foreign"


def test_claude_command_carries_the_isolation_flags(tmp_path: Path) -> None:
    command = claude_command(tmp_path, POSITIVE_SKILL)
    assert command[1] == "-p"
    assert f"/{PLUGIN_NAME}:{POSITIVE_SKILL}" in command[2]
    for flag, value in [
        ("--plugin-dir", str(tmp_path)),
        ("--model", MODEL),
        ("--allowedTools", "Bash"),
        ("--setting-sources", "project"),
        ("--permission-mode", "default"),
    ]:
        assert command[command.index(flag) + 1] == value


def test_run_with_retry_stops_after_a_settled_first_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []

    def fake(*_args: object) -> Observation:
        calls.append(1)
        return _observation("")

    monkeypatch.setattr(support, "run_skill", fake)
    run_with_retry(tmp_path, tmp_path, POSITIVE_SKILL, {}, lambda _obs: True)
    assert len(calls) == 1


def test_run_with_retry_retries_once_then_returns_the_last_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []

    def fake(*_args: object) -> Observation:
        calls.append(1)
        return _observation(f"run {len(calls)}")

    monkeypatch.setattr(support, "run_skill", fake)
    last = run_with_retry(tmp_path, tmp_path, POSITIVE_SKILL, {}, lambda _obs: False)
    assert len(calls) == ATTEMPTS == 2
    assert last.stdout == "run 2"
