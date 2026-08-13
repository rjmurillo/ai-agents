"""Tests for the real-CLI runtime parity evaluator, issue #4853."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.eval._runtime_parity_test_support import FIXTURES, parity


def _completed(
    argv: list[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


class FakeRunner:
    """Dispatch fake CLI output from argv and the fixture file in cwd."""

    def __init__(
        self,
        *,
        claude_model: str = parity.DEFAULT_MODEL,
        copilot_model: str = parity.DEFAULT_MODEL,
        auth_failure: str | None = None,
        fail_prompt_marker: str | None = None,
    ) -> None:
        self.claude_model = claude_model
        self.copilot_model = copilot_model
        self.auth_failure = auth_failure
        self.fail_prompt_marker = fail_prompt_marker
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        args = [str(value) for value in argv]
        self.calls.append(args)
        executable = Path(args[0]).name.lower()
        if "--version" in args:
            return _completed(args, stdout=f"{executable} test-version\n")
        if self.auth_failure == executable:
            return _completed(args, returncode=1, stderr="Not logged in")

        workspace = Path(kwargs["cwd"])
        prompt = (workspace / "PARITY_FIXTURE.md").read_text(encoding="utf-8")
        response = self._response(prompt, workspace)
        if self.fail_prompt_marker and self.fail_prompt_marker in prompt:
            response = "WRONG_RESPONSE"
        if executable.startswith("claude"):
            output = [
                {
                    "type": "system",
                    "subtype": "init",
                    "model": self.claude_model,
                },
                {
                    "type": "assistant",
                    "message": {
                        "content": (
                            [{"type": "tool_use", "name": "Write", "input": {}}]
                            if "parity-result.txt" in prompt
                            else []
                        )
                    },
                },
                {"type": "result", "subtype": "success", "result": response},
            ]
        else:
            output = [
                {
                    "type": "assistant.message",
                    "data": {
                        "content": response,
                        "model": self.copilot_model,
                    },
                }
            ]
            if "parity-result.txt" in prompt:
                output.append(
                    {
                        "type": "tool.execution_start",
                        "data": {"toolName": "write"},
                    }
                )
        return _completed(
            args,
            stdout="\n".join(json.dumps(event) for event in output) + "\n",
        )

    @staticmethod
    def _response(prompt: str, workspace: Path) -> str:
        if "Phases 1 and 2" in prompt:
            return "CONTINUE_PHASE_3"
        if "parity-result.txt" in prompt:
            (workspace / "parity-result.txt").write_text(
                "parity-ok\n", encoding="utf-8"
            )
            return "TOOL_EXECUTED"
        if "deployment choice" in prompt:
            return (
                "A) Canary deployment\n"
                "B) Immediate deployment\n"
                "Recommendation: A"
            )
        return "REJECT_INCOMPLETE\nOnly 16 of 49 promised artifacts are valid."


def _minimal_corpus(tmp_path: Path, *, controls: dict | None = None) -> Path:
    source = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixture = source["fixtures"][0]
    if controls is not None:
        fixture["controls"] = controls
    path = tmp_path / "fixtures.json"
    path.write_text(
        json.dumps({"schema_version": 1, "fixtures": [fixture]}),
        encoding="utf-8",
    )
    return path


def test_committed_fixture_controls_discriminate() -> None:
    fixtures = parity.load_fixtures(FIXTURES)

    assert len(fixtures) == 4
    assert fixtures[1].setup_files == {"parity-result.txt": "pending\n"}
    for fixture in fixtures:
        positive = parity.score_assertions(
            fixture, fixture.positive.response, fixture.positive.files
        )
        negative = parity.score_assertions(
            fixture, fixture.negative.response, fixture.negative.files
        )
        assert all(result["passed"] for result in positive)
        assert not all(result["passed"] for result in negative)


def test_fixture_rejects_agent_path_escape(tmp_path: Path) -> None:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    payload["fixtures"][0]["agents"]["claude"] = "../outside.md"
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(parity.ParityConfigError, match="escapes"):
        parity.load_fixtures(path)


def test_fixture_rejects_unsupported_tool(tmp_path: Path) -> None:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    payload["fixtures"][0]["tools"] = ["read"]
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(parity.ParityConfigError, match="unsupported"):
        parity.load_fixtures(path)


def test_fixture_rejects_positive_control_that_fails(tmp_path: Path) -> None:
    controls = {
        "positive": {"response": "RESTART_PHASE_1", "files": {}},
        "negative": {"response": "RESTART_PHASE_1", "files": {}},
    }

    with pytest.raises(parity.ParityConfigError, match="positive control"):
        parity.load_fixtures(_minimal_corpus(tmp_path, controls=controls))


def test_fixture_rejects_negative_control_that_passes(tmp_path: Path) -> None:
    controls = {
        "positive": {"response": "CONTINUE_PHASE_3", "files": {}},
        "negative": {"response": "CONTINUE_PHASE_3", "files": {}},
    }

    with pytest.raises(parity.ParityConfigError, match="negative control"):
        parity.load_fixtures(_minimal_corpus(tmp_path, controls=controls))


def test_commands_isolate_profiles_and_send_the_same_fixture() -> None:
    fixture = parity.load_fixtures(FIXTURES)[1]

    assert parity.DEFAULT_MODEL == "claude-opus-4.6"
    claude = parity.build_argv("claude", "claude", parity.DEFAULT_MODEL, fixture)
    copilot = parity.build_argv(
        "copilot", "copilot", parity.DEFAULT_MODEL, fixture
    )

    assert "--setting-sources" in claude
    assert claude[claude.index("--setting-sources") + 1] == "project"
    assert "--strict-mcp-config" in claude
    assert "--no-custom-instructions" in copilot
    assert "--disable-builtin-mcps" in copilot
    assert "--no-auto-update" in copilot
    assert "--allow-all-tools" in copilot
    assert "--allow-all-paths" not in copilot
    assert claude[claude.index("--tools") + 1] == "Edit"
    assert "--available-tools=edit" in copilot
    assert claude[claude.index("--print") + 1] == fixture.prompt
    assert copilot[copilot.index("--prompt") + 1] == fixture.prompt
    assert parity._redacted_argv(claude, "claude")[
        claude.index("--print") + 1
    ] == "<fixture-prompt>"
    assert parity._redacted_argv(copilot, "copilot")[
        copilot.index("--prompt") + 1
    ] == "<fixture-prompt>"


def test_runtime_env_uses_isolated_profiles(tmp_path: Path) -> None:
    claude_workspace = tmp_path / "claude"
    copilot_workspace = tmp_path / "copilot"
    claude_workspace.mkdir()
    copilot_workspace.mkdir()

    claude_env = parity.runtime_env(claude_workspace, "claude")
    copilot_env = parity.runtime_env(copilot_workspace, "copilot")

    assert claude_env["CLAUDE_CONFIG_DIR"].startswith(str(claude_workspace))
    assert copilot_env["COPILOT_HOME"].startswith(str(copilot_workspace))
    assert copilot_env["COPILOT_SESSION_STATE_DIR"].startswith(
        str(copilot_workspace)
    )
    assert "COPILOT_PLUGIN_ROOT" not in copilot_env


def test_parsers_capture_models_answers_and_tools() -> None:
    claude_events = [
        {"type": "system", "subtype": "init", "model": "m1"},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Write"},
                    {"type": "tool_use", "name": "Task"},
                ]
            },
        },
        {"type": "result", "result": "done"},
    ]
    copilot_events = [
        {"type": "assistant.message", "data": {"content": "done", "model": "m1"}},
        {"type": "tool.execution_start", "data": {"toolName": "write"}},
        {"type": "subagent.started", "data": {"agentId": "a1"}},
    ]

    assert parity._claude_result(claude_events) == ("done", "m1")
    assert parity._copilot_result(copilot_events) == ("done", "m1")
    claude_tools, claude_subagents = parity._traces(claude_events)
    copilot_tools, copilot_subagents = parity._traces(copilot_events)
    assert len(claude_tools) == 2
    assert len(claude_subagents) == 1
    assert len(copilot_tools) == 1
    assert len(copilot_subagents) == 1


def test_run_evaluation_passes_all_fixtures(tmp_path: Path) -> None:
    output = tmp_path / "run" / "report.json"
    runner = FakeRunner()

    report, code = parity.run_evaluation(
        fixtures_path=FIXTURES,
        model=parity.DEFAULT_MODEL,
        output=output,
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=runner,
    )

    assert code == parity.EXIT_OK
    assert report["verdict"] == "PASS"
    assert output.is_file()
    assert len(report["fixtures"]) == 4
    for record in report["fixtures"]:
        assert record["claude"]["provenance"] == "Claude runtime"
        assert record["copilot"]["provenance"] == "Copilot runtime"
        assert record["claude"]["passed"] is True
        assert record["copilot"]["passed"] is True
        assert record["claude"]["raw_output"]
        assert record["copilot"]["raw_output"]
        assert record["controls"]["provenance"] == "prompt-only"
        assert record["claude_agent_sha256"]
        assert record["copilot_agent_sha256"]
        assert record["fixture_sha256"]


def test_model_mismatch_fails_closed_and_stops(tmp_path: Path) -> None:
    runner = FakeRunner(copilot_model="different-model")

    report, code = parity.run_evaluation(
        fixtures_path=FIXTURES,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=runner,
    )

    assert code == parity.EXIT_LOGIC
    assert report["verdict"] == "FAIL_MODEL_MISMATCH"
    assert len(report["fixtures"]) == 1


def test_behavioral_failure_still_runs_every_fixture(tmp_path: Path) -> None:
    runner = FakeRunner(fail_prompt_marker="Phases 1 and 2")

    report, code = parity.run_evaluation(
        fixtures_path=FIXTURES,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=runner,
    )

    assert code == parity.EXIT_LOGIC
    assert report["verdict"] == "FAIL"
    assert len(report["fixtures"]) == 4


def test_requested_model_override_fails_closed(tmp_path: Path) -> None:
    runner = FakeRunner(claude_model="old-model", copilot_model="old-model")

    report, code = parity.run_evaluation(
        fixtures_path=FIXTURES,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=runner,
    )

    assert code == parity.EXIT_LOGIC
    assert report["verdict"] == "FAIL_MODEL_MISMATCH"
    assert report["fixtures"][0]["claude"]["resolved_model"] == "old-model"


def test_auth_failure_returns_auth_exit_and_stops(tmp_path: Path) -> None:
    runner = FakeRunner(auth_failure="claude")

    report, code = parity.run_evaluation(
        fixtures_path=FIXTURES,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=runner,
    )

    assert code == parity.EXIT_AUTH
    assert report["verdict"] == "ERROR"
    assert len(report["fixtures"]) == 1
    assert "copilot" not in report["fixtures"][0]
    failure = report["fixtures"][0]["claude"]
    assert failure["stderr"] == "Not logged in"
    assert failure["error"] == "Not logged in"


def test_dry_run_executes_versions_only(tmp_path: Path) -> None:
    runner = FakeRunner()

    report, code = parity.run_evaluation(
        fixtures_path=FIXTURES,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=True,
        runner=runner,
    )

    assert code == parity.EXIT_OK
    assert report["verdict"] == "DRY_RUN"
    assert len(runner.calls) == 2
    assert all("--version" in call for call in runner.calls)
    assert all("positive" in record["controls"] for record in report["fixtures"])
    assert all(
        record["controls"]["provenance"] == "prompt-only"
        for record in report["fixtures"]
    )
    assert all(record["claude_agent_sha256"] for record in report["fixtures"])
    assert all(record["copilot_agent_sha256"] for record in report["fixtures"])


def test_existing_output_is_a_config_error(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    output.write_text("{}\n", encoding="utf-8")
    runner = FakeRunner()

    with pytest.raises(parity.ParityConfigError, match="already contains"):
        parity.run_evaluation(
            fixtures_path=FIXTURES,
            model=parity.DEFAULT_MODEL,
            output=output,
            claude_bin="claude",
            copilot_bin="copilot",
            timeout=30,
            dry_run=False,
            runner=runner,
        )

    assert runner.calls == []
    assert not (tmp_path / "version-probes").exists()


def test_main_returns_config_exit_for_invalid_model(capsys) -> None:
    code = parity.main(["--model", "bad model"], runner=FakeRunner())

    assert code == parity.EXIT_CONFIG
    assert "invalid format" in capsys.readouterr().err


def test_main_returns_config_exit_for_bad_fixture(
    tmp_path: Path, capsys
) -> None:
    fixture = tmp_path / "bad.json"
    fixture.write_text("{}", encoding="utf-8")

    code = parity.main(
        ["--fixtures", str(fixture), "--dry-run"],
        runner=FakeRunner(),
    )

    assert code == parity.EXIT_CONFIG
    assert "schema_version" in capsys.readouterr().err


def test_a_question_mechanism_mismatch_fails_the_run(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "run" / "report.json"
    real = parity._run_fixture

    def fake_run_fixture(fixture, harness, *args, **kwargs):
        record, code = real(fixture, harness, *args, **kwargs)
        if harness == "copilot":
            record["question_mechanism"] = "structured_event"
        return record, code

    monkeypatch.setattr(parity, "_run_fixture", fake_run_fixture)

    report, code = parity.run_evaluation(
        fixtures_path=_minimal_corpus(tmp_path),
        model=parity.DEFAULT_MODEL,
        output=output,
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30.0,
        dry_run=False,
        runner=FakeRunner(),
    )

    assert report["verdict"] == "FAIL_QUESTION_MECHANISM_MISMATCH"
    assert code == parity.EXIT_LOGIC


def test_matching_question_mechanisms_are_recorded_and_pass(tmp_path: Path) -> None:
    output = tmp_path / "run" / "report.json"

    report, code = parity.run_evaluation(
        fixtures_path=_minimal_corpus(tmp_path),
        model=parity.DEFAULT_MODEL,
        output=output,
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30.0,
        dry_run=False,
        runner=FakeRunner(),
    )

    fixture = report["fixtures"][0]
    assert fixture["claude"]["question_mechanism"] == "text_fallback"
    assert fixture["copilot"]["question_mechanism"] == "text_fallback"
    assert report["verdict"] != "FAIL_QUESTION_MECHANISM_MISMATCH"
    assert code == parity.EXIT_OK
