"""Tests for the skill-routed Claude Code harness (issue #6737).

Offline: `subprocess.run` is replaced by the shared recorder, so no CLI starts.
The tests pin what makes the arm a fair pair: the skill sits where the CLI
discovers it, the user turn invokes it by name, the control gets the same argv
with no skill, and no metered credential reaches the child.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.eval._cli_transport_test_support import Recorder, _claude_cli, install_runner

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
_ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(_EVAL_DIR))
try:
    import _claude_skill_harness as harness
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH

MODEL = "claude-sonnet-5"


def _stream(
    text: str = "ANSWER",
    model: str = MODEL,
    subtype: str = "success",
    tools: tuple[str, ...] = (),
    skills: tuple[str, ...] = ("demo", "debug"),
    usage: bool = True,
) -> str:
    content: list[dict[str, Any]] = [{"type": "tool_use", "name": name} for name in tools]
    content.append({"type": "text", "text": text})
    events: list[dict[str, Any]] = [
        {
            "type": "system",
            "subtype": "init",
            "claude_code_version": "2.1.307",
            "skills": list(skills),
        },
        {"type": "assistant", "message": {"model": model, "content": content}},
        {
            "type": "result",
            "subtype": subtype,
            "is_error": subtype != "success",
            "result": text,
        },
    ]
    if usage:
        events[-1]["usage"] = {
            "input_tokens": 2,
            "cache_creation_input_tokens": 100,
            "cache_read_input_tokens": 50,
            "output_tokens": 7,
        }
    return "\n".join(json.dumps(event) for event in events)


@pytest.fixture
def claude_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "metered-key")
    return monkeypatch


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    root = tmp_path / "src" / "demo"
    (root / "references").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: demo\n---\nSKILL BODY\n", encoding="utf-8")
    (root / "references" / "ref.md").write_text("REF\n", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_bytes(b"\0")
    return root


def _workspace_snapshot(record: dict[str, Any], seen: dict[str, Any]) -> None:
    workspace = Path(record["cwd"])
    seen["files"] = sorted(
        str(path.relative_to(workspace)) for path in workspace.rglob("*") if path.is_file()
    )
    seen["stdin"] = record["input"]
    seen["env"] = record["env"]


class TestPrompt:
    def test_bare_request_when_no_skill(self) -> None:
        assert harness.harness_prompt("  do X  ", None) == "do X"

    def test_slash_invocation_when_skill(self) -> None:
        assert harness.harness_prompt("do X", "spec") == "/spec do X"

    @pytest.mark.parametrize("name", ["", "Spec", "spec x", "spec\n/other", "-spec", "a" * 65])
    def test_refuses_a_name_that_is_not_a_slash_command(self, name: str) -> None:
        assert harness.skill_name_error(name) is not None
        with pytest.raises(ValueError, match="not a slash command name"):
            harness.harness_prompt("do X", name)

    @pytest.mark.parametrize("name", ["spec", "pr-review", "a1"])
    def test_accepts_a_slash_command_name(self, name: str) -> None:
        assert harness.skill_name_error(name) is None


class TestArgv:
    def test_loads_project_settings_and_no_tools(self) -> None:
        argv = harness.build_argv("claude", MODEL)
        assert argv[argv.index("--setting-sources") + 1] == "project"
        assert argv[argv.index("--tools") + 1] == ""
        assert argv[argv.index("--output-format") + 1] == "stream-json"
        assert argv[argv.index("--model") + 1] == MODEL
        assert "--strict-mcp-config" in argv

    def test_keeps_slash_commands_enabled(self) -> None:
        # --disable-slash-commands disables every skill, so the arm could not load one.
        assert "--disable-slash-commands" not in harness.build_argv("claude", MODEL)


class TestRunHarness:
    def test_installs_the_skill_and_invokes_it(
        self, claude_env: pytest.MonkeyPatch, skill_dir: Path
    ) -> None:
        seen: dict[str, Any] = {}
        recorder = Recorder(stdout=_stream(), on_call=lambda r: _workspace_snapshot(r, seen))
        install_runner(claude_env, recorder)

        reply = harness.run_harness("do X", model=MODEL, skill_dir=skill_dir, skill_name="demo")

        assert seen["files"] == [
            ".claude/skills/demo/SKILL.md",
            ".claude/skills/demo/references/ref.md",
        ]
        assert seen["stdin"] == "/demo do X"
        assert reply.text == "ANSWER"
        assert reply.invocation == "/demo"
        assert reply.model == MODEL
        assert reply.input_tokens_total == 152
        assert reply.output_tokens == 7
        assert reply.cli_version == "2.1.307"
        assert reply.credential_step is not None

    def test_control_gets_an_empty_workspace_and_the_same_argv(
        self, claude_env: pytest.MonkeyPatch, skill_dir: Path
    ) -> None:
        seen: dict[str, Any] = {}
        recorder = Recorder(stdout=_stream(), on_call=lambda r: _workspace_snapshot(r, seen))
        install_runner(claude_env, recorder)

        harness.run_harness("do X", model=MODEL, skill_dir=skill_dir, skill_name="demo")
        routed_argv = recorder.argv
        reply = harness.run_harness("do X", model=MODEL, skill_dir=None, skill_name=None)

        assert seen["files"] == []
        assert seen["stdin"] == "do X"
        assert recorder.argv == routed_argv
        assert reply.invocation is None

    def test_metered_credentials_never_reach_the_child(
        self, claude_env: pytest.MonkeyPatch, skill_dir: Path
    ) -> None:
        seen: dict[str, Any] = {}
        install_runner(
            claude_env, Recorder(stdout=_stream(), on_call=lambda r: _workspace_snapshot(r, seen))
        )

        harness.run_harness("do X", model=MODEL, skill_dir=skill_dir, skill_name="demo")

        for name in _claude_cli._BLOCKED_BILLING_ENV:
            assert name not in seen["env"]

    def test_refuses_a_served_model_outside_the_requested_family(
        self, claude_env: pytest.MonkeyPatch
    ) -> None:
        install_runner(claude_env, Recorder(stdout=_stream(model="claude-haiku-4-5")))
        with pytest.raises(RuntimeError, match="model attribution mismatch"):
            harness.run_harness("do X", model=MODEL, skill_dir=None, skill_name=None)

    def test_refuses_an_incomplete_stream(self, claude_env: pytest.MonkeyPatch) -> None:
        install_runner(claude_env, Recorder(stdout=_stream(subtype="error_during_execution")))
        with pytest.raises(RuntimeError, match="did not complete"):
            harness.run_harness("do X", model=MODEL, skill_dir=None, skill_name=None)

    def test_refuses_a_stream_with_no_result_event(self, claude_env: pytest.MonkeyPatch) -> None:
        install_runner(claude_env, Recorder(stdout=_stream().rsplit("\n", 1)[0]))
        with pytest.raises(RuntimeError, match="no result event"):
            harness.run_harness("do X", model=MODEL, skill_dir=None, skill_name=None)

    def test_refuses_an_empty_answer(self, claude_env: pytest.MonkeyPatch) -> None:
        install_runner(claude_env, Recorder(stdout=_stream(text="  ")))
        with pytest.raises(RuntimeError, match="no answer text"):
            harness.run_harness("do X", model=MODEL, skill_dir=None, skill_name=None)

    def test_a_failed_process_raises(self, claude_env: pytest.MonkeyPatch) -> None:
        install_runner(claude_env, Recorder(returncode=1, stderr="boom"))
        with pytest.raises(RuntimeError, match="exited with code 1"):
            harness.run_harness("do X", model=MODEL, skill_dir=None, skill_name=None)

    def test_records_tool_calls(self, claude_env: pytest.MonkeyPatch) -> None:
        install_runner(claude_env, Recorder(stdout=_stream(tools=("Skill",))))
        reply = harness.run_harness("do X", model=MODEL, skill_dir=None, skill_name=None)
        assert reply.tool_calls == ("Skill",)

    def test_skill_dir_and_name_go_together(self, skill_dir: Path) -> None:
        with pytest.raises(ValueError, match="together"):
            harness.run_harness("do X", model=MODEL, skill_dir=skill_dir, skill_name=None)
        with pytest.raises(ValueError, match="together"):
            harness.run_harness("do X", model=MODEL, skill_dir=None, skill_name="demo")

    def test_refuses_a_directory_without_skill_md(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="no SKILL.md"):
            harness.run_harness("do X", model=MODEL, skill_dir=tmp_path, skill_name="demo")

    def test_refuses_a_turn_whose_init_does_not_list_the_skill(
        self, claude_env: pytest.MonkeyPatch, skill_dir: Path
    ) -> None:
        install_runner(claude_env, Recorder(stdout=_stream(skills=("debug",))))
        with pytest.raises(RuntimeError, match="did not list the installed skill"):
            harness.run_harness("do X", model=MODEL, skill_dir=skill_dir, skill_name="demo")

    def test_control_does_not_need_a_skill_list(self, claude_env: pytest.MonkeyPatch) -> None:
        install_runner(claude_env, Recorder(stdout=_stream(skills=())))
        reply = harness.run_harness("do X", model=MODEL, skill_dir=None, skill_name=None)
        assert reply.text == "ANSWER"

    def test_refuses_a_turn_cut_at_a_limit(self, claude_env: pytest.MonkeyPatch) -> None:
        install_runner(claude_env, Recorder(stdout=_stream(subtype="error_max_turns")))
        with pytest.raises(RuntimeError, match="error_max_turns"):
            harness.run_harness("do X", model=MODEL, skill_dir=None, skill_name=None)

    def test_missing_usage_is_none_not_zero(self, claude_env: pytest.MonkeyPatch) -> None:
        install_runner(claude_env, Recorder(stdout=_stream(usage=False)))
        reply = harness.run_harness("do X", model=MODEL, skill_dir=None, skill_name=None)
        assert reply.input_tokens_total is None
        assert reply.output_tokens is None

    def test_refuses_instruction_files_above_the_sandbox(
        self, claude_env: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        checkout = tmp_path / "checkout"
        (checkout / "scratch").mkdir(parents=True)
        (checkout / "CLAUDE.md").write_text("rules", encoding="utf-8")
        claude_env.setattr(harness.tempfile, "gettempdir", lambda: str(checkout / "scratch"))
        install_runner(claude_env, Recorder(stdout=_stream()))
        with pytest.raises(RuntimeError, match="sits under instruction files"):
            harness.run_harness("do X", model=MODEL, skill_dir=None, skill_name=None)

    def test_ambient_scan_walks_up_to_ancestors(self, tmp_path: Path) -> None:
        (tmp_path / "a" / "b").mkdir(parents=True)
        (tmp_path / "a" / ".claude").mkdir()
        found = harness.ambient_instruction_paths(tmp_path / "a" / "b")
        assert (tmp_path / "a" / ".claude").resolve() in found
        assert not [p for p in found if (tmp_path / "a" / "b").resolve() in p.parents]

    def test_a_copy_failure_is_a_runtime_error(
        self, claude_env: pytest.MonkeyPatch, skill_dir: Path
    ) -> None:
        (skill_dir / "broken").symlink_to(skill_dir / "missing-target")
        install_runner(claude_env, Recorder(stdout=_stream(), on_call=lambda r: None))
        with pytest.raises(RuntimeError, match="could not install skill"):
            harness.run_harness("do X", model=MODEL, skill_dir=skill_dir, skill_name="demo")
