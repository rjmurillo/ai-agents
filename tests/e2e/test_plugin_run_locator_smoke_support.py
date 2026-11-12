#!/usr/bin/env python3
"""Unit tests of the ADR-121 locator smoke helpers (no CLI, no model call)."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

# tests/e2e is not on sys.path under --import-mode=importlib (no __init__.py). The
# edit is undone once the imports are bound, so it cannot leak into later tests.
_original_sys_path = sys.path.copy()
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "build" / "scripts"))
    import plugin_run_locator_smoke_support as support
    import smoke_skip_policy
    from plugin_run_launcher import render_locator
    from plugin_run_locator_smoke_support import (
        ATTEMPTS,
        LEGACY_COMMAND,
        LEGACY_SKILL,
        MARKER,
        MODEL,
        PERMISSION_MODE,
        PLUGIN_NAME,
        POSITIVE_SKILL,
        RESOLVER_SOURCE,
        STUB_SOURCE,
        TARGET_ARG,
        TARGET_REL,
        BashCall,
        Observation,
        build_plugin,
        claude_command,
        gate_skip_reason,
        observe,
        parse_stream,
        run_skill,
        run_with_retry,
        smoke_env,
    )
finally:
    sys.path[:] = _original_sys_path

MARKER_LINE = json.dumps({"marker": MARKER, "argv": [TARGET_ARG]})


def _stream(*events: Mapping[str, object]) -> str:
    return "\n".join(json.dumps(event) for event in events)


def _bash_use(command: str, use_id: str = "t1") -> dict[str, object]:
    block = {"type": "tool_use", "id": use_id, "name": "Bash", "input": {"command": command}}
    return {"type": "assistant", "message": {"content": [block]}}


def _tool_result(content: object, use_id: str = "t1") -> dict[str, object]:
    block = {"type": "tool_result", "tool_use_id": use_id, "content": content}
    return {"type": "user", "message": {"content": [block]}}


def _locator_command(plugin: Path) -> str:
    """The rendered locator after the host swaps ``${CLAUDE_PLUGIN_ROOT}`` for the plugin dir."""
    return render_locator(TARGET_REL, TARGET_ARG).replace("${CLAUDE_PLUGIN_ROOT}", str(plugin))


def _run_of(command: str, result: object) -> Observation:
    return _observation(_stream(_bash_use(command), _tool_result(result)))


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


def test_parse_stream_pairs_each_bash_call_with_its_result_by_id() -> None:
    stdout = _stream(
        {"type": "system"},
        _bash_use("echo a", "ta"),
        _bash_use("echo b", "tb"),
        _tool_result("b-out", "tb"),
        _tool_result([{"type": "text", "text": "a-out"}], "ta"),
    )
    assert parse_stream(stdout) == (BashCall("echo a", "a-out"), BashCall("echo b", "b-out"))


def test_parse_stream_keeps_a_call_with_no_result_as_none() -> None:
    assert parse_stream(_stream(_bash_use("sleep 1"))) == (BashCall("sleep 1", None),)


def test_parse_stream_ignores_a_result_with_no_matching_tool_use_id() -> None:
    stdout = _stream(_bash_use("echo hi", "t1"), _tool_result(MARKER_LINE, "other"))
    assert parse_stream(stdout) == (BashCall("echo hi", None),)
    assert parse_stream(_stream(_tool_result(MARKER_LINE, "orphan"))) == ()


def test_parse_stream_ignores_results_of_non_bash_tools() -> None:
    read = {"type": "tool_use", "id": "r1", "name": "Read", "input": {"file_path": "x"}}
    stdout = _stream({"type": "assistant", "message": {"content": [read]}}, _tool_result("x", "r1"))
    assert parse_stream(stdout) == ()


def test_parse_stream_skips_junk_lines_and_odd_shapes() -> None:
    stdout = "\n".join(
        [
            "not json",
            "[1, 2]",
            _stream({"type": "assistant", "message": {"content": "plain text"}}),
            _stream({"type": "assistant", "message": "odd"}),
            _stream(_tool_result(None)),
        ]
    )
    assert parse_stream(stdout) == ()


def test_parse_stream_on_empty_output() -> None:
    assert parse_stream("") == ()


def test_observation_exposes_commands_and_results_of_paired_calls() -> None:
    seen = _run_of("echo hi", "hi")
    assert seen.bash_commands == ("echo hi",)
    assert seen.tool_results == ("hi",)


def test_locator_ran_accepts_the_marker_from_the_locator_command(tmp_path: Path) -> None:
    seen = _run_of(_locator_command(tmp_path), f"noise\n{MARKER_LINE}")
    assert seen.locator_ran(tmp_path)


def test_locator_ran_rejects_a_marker_from_a_directly_run_stub(tmp_path: Path) -> None:
    direct = f"python3 {tmp_path / TARGET_REL} {TARGET_ARG}"
    assert not _run_of(direct, MARKER_LINE).locator_ran(tmp_path)


def test_locator_ran_rejects_a_locator_with_the_token_left_literal(tmp_path: Path) -> None:
    literal = render_locator(TARGET_REL, TARGET_ARG)
    assert not _run_of(literal, MARKER_LINE).locator_ran(tmp_path)


def test_locator_ran_rejects_a_locator_for_another_plugin_directory(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    other = tmp_path / "elsewhere"
    assert not _run_of(_locator_command(other), MARKER_LINE).locator_ran(plugin)


def test_locator_ran_ignores_a_result_with_no_matching_tool_use_id(tmp_path: Path) -> None:
    stdout = _stream(_bash_use(_locator_command(tmp_path), "t1"), _tool_result(MARKER_LINE, "x"))
    assert not _observation(stdout).locator_ran(tmp_path)


def test_locator_ran_needs_the_marker_and_the_argument(tmp_path: Path) -> None:
    command = _locator_command(tmp_path)
    wrong_arg = json.dumps({"marker": MARKER, "argv": []})
    assert not _run_of(command, wrong_arg).locator_ran(tmp_path)
    assert not _run_of(command, "no json here").locator_ran(tmp_path)
    assert not _run_of(command, None).locator_ran(tmp_path)


def test_marker_in_model_prose_alone_is_not_a_run(tmp_path: Path) -> None:
    prose = {"type": "assistant", "message": {"content": [{"type": "text", "text": MARKER}]}}
    seen = _observation(_stream(prose))
    assert seen.marker_anywhere()
    assert not seen.locator_ran(tmp_path)


def test_legacy_attempted_needs_a_bash_call_holding_the_legacy_form() -> None:
    assert _run_of(LEGACY_COMMAND, "No such file").legacy_attempted()
    assert not _run_of("true", "").legacy_attempted()
    assert not _observation("").legacy_attempted()


def test_legacy_leaked_sees_a_marker_in_any_paired_result() -> None:
    assert _run_of(LEGACY_COMMAND, MARKER_LINE).legacy_leaked()
    assert not _run_of(LEGACY_COMMAND, "No such file").legacy_leaked()


def test_legacy_leaked_sees_a_marker_in_the_model_output() -> None:
    prose = {"type": "assistant", "message": {"content": [{"type": "text", "text": MARKER}]}}
    assert _observation(_stream(prose)).legacy_leaked()


def test_a_model_that_ran_true_does_not_satisfy_the_legacy_control() -> None:
    seen = _run_of("true", "")
    assert not seen.legacy_attempted()
    assert not seen.legacy_leaked()


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
        ("--permission-mode", PERMISSION_MODE),
    ]:
        assert command[command.index(flag) + 1] == value
    assert PERMISSION_MODE == "dontAsk"


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


def _timeout(stdout: bytes | str | None, stderr: bytes | str | None) -> subprocess.TimeoutExpired:
    return subprocess.TimeoutExpired(["claude"], 170, output=stdout, stderr=stderr)


def _raise_timeout(exc: subprocess.TimeoutExpired) -> object:
    def fake(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise exc

    return fake


@pytest.mark.parametrize(
    "stdout",
    [b'{"api_error_status": 429}', '{"api_error_status": 429}'],
    ids=["bytes", "str"],
)
def test_run_skill_timeout_with_a_quota_marker_skips_with_the_quota_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, stdout: bytes | str
) -> None:
    monkeypatch.setattr(subprocess, "run", _raise_timeout(_timeout(stdout, None)))
    with pytest.raises(pytest.skip.Exception) as caught:
        run_skill(tmp_path, tmp_path, POSITIVE_SKILL, {})
    assert str(caught.value).startswith(smoke_skip_policy.QUOTA_SKIP_MARKER)


def test_run_skill_timeout_with_an_auth_marker_in_stderr_is_not_a_quota_skip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(subprocess, "run", _raise_timeout(_timeout(None, b"OAuth session expired")))
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(pytest.skip.Exception) as caught:
        run_skill(tmp_path, tmp_path, POSITIVE_SKILL, {})
    assert "OAuth session expired" in str(caught.value)
    assert not str(caught.value).startswith(smoke_skip_policy.QUOTA_SKIP_MARKER)


def test_run_skill_timeout_with_no_marker_fails_in_ci_and_shows_the_tail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(subprocess, "run", _raise_timeout(_timeout(b"hung output", None)))
    monkeypatch.setenv("CI", "true")
    with pytest.raises(pytest.fail.Exception, match="no block marker.*hung output"):
        run_skill(tmp_path, tmp_path, POSITIVE_SKILL, {})


def test_run_skill_timeout_with_no_marker_skips_locally_without_the_quota_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(subprocess, "run", _raise_timeout(_timeout(None, None)))
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with pytest.raises(pytest.skip.Exception) as caught:
        run_skill(tmp_path, tmp_path, POSITIVE_SKILL, {})
    assert not str(caught.value).startswith(smoke_skip_policy.QUOTA_SKIP_MARKER)


def test_run_skill_returns_the_observation_of_a_finished_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    done = subprocess.CompletedProcess([], 0, _stream(_bash_use("true"), _tool_result("")), "")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: done)
    assert run_skill(tmp_path, tmp_path, POSITIVE_SKILL, {}).bash_commands == ("true",)


def test_run_skill_skips_a_failed_run_that_names_a_quota_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blocked = subprocess.CompletedProcess([], 1, "", "credit balance is too low")
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: blocked)
    with pytest.raises(pytest.skip.Exception):
        run_skill(tmp_path, tmp_path, POSITIVE_SKILL, {})
