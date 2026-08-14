"""Regression tests for the runtime-parity review findings on PR #4877."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.eval._runtime_parity_test_support import FIXTURES, parity, runtime_parity


@pytest.mark.parametrize("bad_id", ["/abs/fixture", "../escape", "a/../../b"])
def test_fixture_id_that_leaves_the_workspace_is_a_config_error(
    tmp_path: Path, bad_id: str
) -> None:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    payload["fixtures"] = [payload["fixtures"][0]]
    payload["fixtures"][0]["id"] = bad_id
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(parity.ParityConfigError) as excinfo:
        parity.load_fixtures(path)

    assert "fixtures[0].id" in str(excinfo.value)


def test_an_ordinary_fixture_id_still_loads(tmp_path: Path) -> None:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    payload["fixtures"] = [payload["fixtures"][0]]
    payload["fixtures"][0]["id"] = "plain-id"
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert parity.load_fixtures(path)[0].fixture_id == "plain-id"


def test_agent_install_preserves_crlf_line_endings(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_bytes(b"---\r\nname: original\r\n---\r\nbody\r\n")
    target = tmp_path / "target.md"
    runtime_parity._install_agent(source, target)

    assert target.read_bytes() == b"---\r\nname: parity\r\n---\r\nbody\r\n"


def test_runtime_env_redirects_every_home_and_cache_root(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", "/operator/home")
    monkeypatch.setenv("USERPROFILE", "/operator/home")
    monkeypatch.setenv("LOCALAPPDATA", "/operator/AppData/Local")
    monkeypatch.setenv("APPDATA", "/operator/AppData/Roaming")
    monkeypatch.setenv("XDG_CACHE_HOME", "/operator/cache")
    monkeypatch.setenv("COPILOT_CACHE_HOME", "/operator/copilot-cache")
    workspace = tmp_path / "copilot"
    workspace.mkdir()

    env = parity.runtime_env(workspace, "copilot")

    redirected = (
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "COPILOT_CACHE_HOME",
    )
    for key in redirected:
        assert env[key].startswith(str(workspace)), key
        assert Path(env[key]).is_dir(), key
    assert not any(value.startswith("/operator") for value in env.values())


def test_the_claude_harness_is_profile_isolated_too(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", "/operator/home")
    workspace = tmp_path / "claude"
    workspace.mkdir()

    env = parity.runtime_env(workspace, "claude")

    assert env["HOME"].startswith(str(workspace))
    assert env["CLAUDE_CONFIG_DIR"].startswith(str(workspace))


def test_each_harness_receives_only_its_own_credentials(
    tmp_path: Path, monkeypatch
) -> None:
    credentials = {
        "ANTHROPIC_API_KEY": "anthropic",
        "CLAUDE_CODE_OAUTH_TOKEN": "claude-oauth",
        "COPILOT_GITHUB_TOKEN": "copilot",
        "GH_TOKEN": "gh",
        "GITHUB_TOKEN": "github",
    }
    for key, value in credentials.items():
        monkeypatch.setenv(key, value)
    claude_workspace = tmp_path / "claude"
    copilot_workspace = tmp_path / "copilot"
    claude_workspace.mkdir()
    copilot_workspace.mkdir()

    claude_env = parity.runtime_env(claude_workspace, "claude")
    copilot_env = parity.runtime_env(copilot_workspace, "copilot")

    assert claude_env["ANTHROPIC_API_KEY"] == "anthropic"
    assert claude_env["CLAUDE_CODE_OAUTH_TOKEN"] == "claude-oauth"
    assert "COPILOT_GITHUB_TOKEN" not in claude_env
    assert "GH_TOKEN" not in claude_env
    assert "GITHUB_TOKEN" not in claude_env
    assert copilot_env["COPILOT_GITHUB_TOKEN"] == "copilot"
    assert copilot_env["GH_TOKEN"] == "gh"
    assert copilot_env["GITHUB_TOKEN"] == "github"
    assert "ANTHROPIC_API_KEY" not in copilot_env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in copilot_env


def test_an_unattributed_final_message_reports_no_model() -> None:
    events = [
        {"type": "assistant.message", "data": {"content": "", "model": "m1"}},
        {"type": "assistant.message", "data": {"content": "done"}},
    ]

    assert parity._copilot_result(events) == ("done", None)


def test_a_mixed_model_sequence_reports_no_model() -> None:
    events = [
        {"type": "assistant.message", "data": {"content": "part", "model": "m1"}},
        {"type": "assistant.message", "data": {"content": "done", "model": "m2"}},
    ]

    assert parity._copilot_result(events) == ("part\ndone", None)


def test_every_content_bearing_message_attributed_reports_the_model() -> None:
    events = [
        {"type": "assistant.message", "data": {"content": "part", "model": "m1"}},
        {"type": "assistant.message", "data": {"content": "done", "model": "m1"}},
    ]

    assert parity._copilot_result(events) == ("part\ndone", "m1")


def test_earlier_copilot_message_is_included_in_assertion_scoring() -> None:
    events = [
        {
            "type": "assistant.message",
            "data": {"content": "RESTART_PHASE_1", "model": "m1"},
        },
        {
            "type": "assistant.message",
            "data": {"content": "CONTINUE_PHASE_3", "model": "m1"},
        },
    ]
    fixture = next(
        fixture
        for fixture in parity.load_fixtures(FIXTURES)
        if fixture.fixture_id == "resume-phase-3"
    )

    response, _ = parity._copilot_result(events)
    results = parity.score_assertions(fixture, response, {})

    assert results[0]["passed"] is False
    assert results[1]["passed"] is False


def test_no_content_reports_no_model() -> None:
    events = [{"type": "assistant.message", "data": {"content": "  ", "model": "m1"}}]

    assert parity._copilot_result(events) == ("", None)


def test_a_version_probe_timeout_returns_the_external_exit_code(capsys) -> None:
    def timing_out_runner(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout", 1))

    code = parity.main(["--dry-run"], runner=timing_out_runner)

    assert code == parity.EXIT_EXTERNAL
    assert "Error:" in capsys.readouterr().err


def test_a_runtime_timeout_writes_the_standard_failure_record(
    tmp_path: Path,
) -> None:
    output = tmp_path / "report.json"

    def timing_out_runtime(argv, **kwargs):
        args = [str(value) for value in argv]
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, "test-version\n", "")
        raise subprocess.TimeoutExpired(args, kwargs.get("timeout", 1))

    code = parity.main(
        [
            "--fixtures",
            str(FIXTURES),
            "--output",
            str(output),
            "--timeout",
            "30",
        ],
        runner=timing_out_runtime,
    )

    record = json.loads(output.read_text(encoding="utf-8"))["fixtures"][0]["claude"]
    assert code == parity.EXIT_EXTERNAL
    assert record["provenance"] == "Claude runtime"
    assert record["command"][0] == "claude"
    assert record["exit_code"] is None
    assert record["resolved_model"] is None
    assert record["raw_output"] == ""
    assert record["stderr"] == ""
    assert record["response"] == ""
    assert record["question_mechanism"] is None
    assert record["tool_events"] == []
    assert record["subagent_events"] == []
    assert record["assertions"] == []
    assert record["error"] == "runtime timed out"
    assert record["passed"] is False


@pytest.mark.parametrize(
    ("bad_line", "expected_error"),
    [
        ("not-json", "is not valid JSON"),
        ("[]", "must be a JSON object"),
    ],
)
def test_malformed_jsonl_is_an_external_runtime_failure(
    tmp_path: Path,
    capsys,
    bad_line: str,
    expected_error: str,
) -> None:
    output = tmp_path / "report.json"

    def malformed_runner(argv, **kwargs):
        args = [str(value) for value in argv]
        executable = Path(args[0]).name.lower()
        if "--version" in args:
            return subprocess.CompletedProcess(
                args, 0, f"{executable} test-version\n", ""
            )
        response = "CONTINUE_PHASE_3"
        if executable.startswith("claude"):
            events = [
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "model": parity.DEFAULT_MODEL,
                    }
                ),
                bad_line,
                json.dumps(
                    {"type": "result", "subtype": "success", "result": response}
                ),
            ]
        else:
            events = [
                json.dumps(
                    {
                        "type": "assistant.message",
                        "data": {
                            "content": response,
                            "model": parity.DEFAULT_MODEL,
                        },
                    }
                )
            ]
        return subprocess.CompletedProcess(
            args, 0, "\n".join(events) + "\n", ""
        )

    code = parity.main(
        [
            "--fixtures",
            str(FIXTURES),
            "--output",
            str(output),
            "--timeout",
            "30",
        ],
        runner=malformed_runner,
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert code == parity.EXIT_EXTERNAL
    assert report["verdict"] == "ERROR"
    assert expected_error in report["fixtures"][0]["claude"]["error"]
    capsys.readouterr()


def test_consequential_choice_exposes_each_question_capability() -> None:
    fixture = next(
        fixture
        for fixture in parity.load_fixtures(FIXTURES)
        if fixture.fixture_id == "consequential-choice"
    )

    claude = parity.build_argv(
        "claude", "claude", parity.DEFAULT_MODEL, fixture
    )
    copilot = parity.build_argv(
        "copilot", "copilot", parity.DEFAULT_MODEL, fixture
    )

    assert claude[claude.index("--tools") + 1] == "AskUserQuestion"
    assert "--available-tools=ask_user" in copilot
    assert "--allow-tool=ask_user" in copilot
    assert "--no-ask-user" not in copilot


class TestTheAgentIsRegisteredUnderTheNameTheCliIsInvokedWith:
    """Both CLIs resolve --agent against the frontmatter name, not the filename."""

    def _fixture(self):
        return next(
            f
            for f in parity.load_fixtures(FIXTURES)
            if f.fixture_id == "consequential-choice"
        )

    def test_the_claude_agent_frontmatter_name_becomes_parity(self, tmp_path: Path):
        fixture = self._fixture()
        source_name = fixture.claude_agent.read_text(encoding="utf-8").splitlines()[1]
        workspace = tmp_path / "claude"

        parity.prepare_workspace(fixture, "claude", workspace)

        installed = workspace / ".claude" / "agents" / "parity.md"
        assert installed.read_text(encoding="utf-8").splitlines()[1] == "name: parity"
        assert source_name != "name: parity", "fixture no longer exercises the rename"

    def test_the_copilot_agent_frontmatter_name_becomes_parity(self, tmp_path: Path):
        fixture = self._fixture()
        workspace = tmp_path / "copilot"

        parity.prepare_workspace(fixture, "copilot", workspace)

        installed = workspace / ".github" / "agents" / "parity.agent.md"
        assert installed.read_text(encoding="utf-8").splitlines()[1] == "name: parity"

    def test_the_body_below_the_frontmatter_is_preserved(self, tmp_path: Path):
        fixture = self._fixture()
        workspace = tmp_path / "claude"

        parity.prepare_workspace(fixture, "claude", workspace)

        source = fixture.claude_agent.read_text(encoding="utf-8")
        installed = (workspace / ".claude" / "agents" / "parity.md").read_text(
            encoding="utf-8"
        )
        assert installed.endswith(source.split("---", 2)[2])

    def _fixture_with_agent(self, agent: Path):
        template = self._fixture()
        return parity.Fixture(
            fixture_id=template.fixture_id,
            claude_agent=agent,
            copilot_agent=agent,
            prompt=template.prompt,
            setup_files={},
            tools=(),
            assertions=template.assertions,
            positive=template.positive,
            negative=template.negative,
        )

    @pytest.mark.parametrize(
        ("name", "content"),
        [
            ("bare.md", "# no frontmatter\n"),
            ("nameless.md", "---\ndescription: x\n---\nbody\n"),
        ],
    )
    def test_an_agent_the_cli_cannot_be_pointed_at_is_a_config_error(
        self, tmp_path: Path, name: str, content: str
    ):
        source = tmp_path / name
        source.write_text(content, encoding="utf-8")

        with pytest.raises(parity.ParityConfigError):
            parity.prepare_workspace(
                self._fixture_with_agent(source), "claude", tmp_path / "ws"
            )


class TestQuestionMechanismClassifier:
    """The report names which branch the harness took to pose its question."""

    def test_a_claude_question_tool_call_reports_a_structured_event(self):
        tools = [{"type": "tool_use", "name": "AskUserQuestion"}]

        assert parity.question_mechanism(tools, "anything") == "structured_event"

    def test_a_copilot_question_event_reports_a_structured_event(self):
        tools = [{"type": "tool.execution_start", "data": {"toolName": "ask_user"}}]

        assert parity.question_mechanism(tools, "anything") == "structured_event"

    def test_prose_with_no_question_tool_reports_the_text_fallback(self):
        tools = [{"type": "tool_use", "name": "Edit"}]

        assert (
            parity.question_mechanism(tools, "Should we do A or B?") == "text_fallback"
        )

    def test_no_tools_and_no_response_reports_no_answer(self):
        assert parity.question_mechanism([], "   ") == "no_answer"
