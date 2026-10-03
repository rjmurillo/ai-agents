"""Tests for scripts/ci/invoke_claude_review.py (issue #5738). Mocked I/O only."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from scripts.ci import invoke_claude_review as claude
from scripts.ci import parse_ai_review_output as parser

VALID_REPLY = "Analysis.\nVERDICT: PASS\nMESSAGE: all requirements covered"


class FakeClient:
    """Stands in for anthropic.Anthropic; records the request, no network."""

    reply: object = None
    error: Exception | None = None
    last_kwargs: dict | None = None
    init_kwargs: dict | None = None

    def __init__(self, **kwargs):
        type(self).init_kwargs = kwargs
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        type(self).last_kwargs = kwargs
        if type(self).error is not None:
            raise type(self).error
        return type(self).reply


def text_reply(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


@pytest.fixture(autouse=True)
def fake_anthropic(monkeypatch):
    FakeClient.reply = text_reply(VALID_REPLY)
    FakeClient.error = None
    FakeClient.last_kwargs = None
    FakeClient.init_kwargs = None
    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    context = tmp_path / "context.md"
    context.write_text("diff content", encoding="utf-8")
    values = {
        "AI_REVIEW_OUTPUT_FILE": str(tmp_path / "verdict.txt"),
        "GITHUB_OUTPUT": str(tmp_path / "github-output.txt"),
        "TIMEOUT_MINUTES": "3",
        "REVIEW_AGENT": "analyst",
        "CONTEXT_MODE": "full",
        "CONTEXT_FILE": str(context),
        "ADDITIONAL_CONTEXT": "spec text",
        "ANTHROPIC_API_KEY": "sk-ant-test-value",
    }
    return values


def run_main(env: dict[str, str]) -> int:
    config = claude.build_config(env)
    return claude.run(config, env)


def verdict_file(env) -> str:
    return Path(env["AI_REVIEW_OUTPUT_FILE"]).read_text(encoding="utf-8")


def outputs(env) -> str:
    return Path(env["GITHUB_OUTPUT"]).read_text(encoding="utf-8")


def parse_verdict(env, monkeypatch, tmp_path) -> str:
    out = tmp_path / "parse-output.txt"
    monkeypatch.setenv("AI_REVIEW_OUTPUT_FILE", env["AI_REVIEW_OUTPUT_FILE"])
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert parser.main() == 0
    return out.read_text(encoding="utf-8")


def test_valid_response_passes_and_verdict_parser_is_unchanged(env, monkeypatch, tmp_path):
    assert run_main(env) == 0

    assert "VERDICT: PASS" in verdict_file(env)
    assert "infrastructure_failure=false" in outputs(env)
    assert "verdict=PASS" in parse_verdict(env, monkeypatch, tmp_path)
    assert FakeClient.last_kwargs["model"] == claude.DEFAULT_CLAUDE_MODEL
    assert FakeClient.init_kwargs["api_key"] == "sk-ant-test-value"
    assert FakeClient.init_kwargs["timeout"] == 180


def test_model_override_and_agent_system_prompt(env, tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "analyst.md").write_text("You are the analyst.", encoding="utf-8")
    env["CLAUDE_MODEL"] = "claude-opus-5-5"

    assert run_main(env) == 0

    assert FakeClient.last_kwargs["model"] == "claude-opus-5-5"
    assert FakeClient.last_kwargs["system"] == "You are the analyst."
    assert "spec text" in FakeClient.last_kwargs["messages"][0]["content"]


def test_no_system_prompt_when_agent_file_absent(env):
    assert run_main(env) == 0
    assert "system" not in FakeClient.last_kwargs


@pytest.mark.parametrize("key", ["", "   "])
def test_missing_secret_fails_closed_with_named_error(env, capsys, key):
    env["ANTHROPIC_API_KEY"] = key

    assert run_main(env) == 0

    out = capsys.readouterr().out
    assert "::error::ANTHROPIC_API_KEY secret is not configured" in out
    body = verdict_file(env)
    assert "VERDICT: DID_NOT_RUN" in body
    assert "ANTHROPIC_API_KEY" in body
    assert "infrastructure_failure=true" in outputs(env)
    assert FakeClient.last_kwargs is None


def test_missing_secret_variable_fails_closed(env):
    del env["ANTHROPIC_API_KEY"]
    assert run_main(env) == 0
    assert "infrastructure_failure=true" in outputs(env)


@pytest.mark.parametrize(
    "error",
    [
        anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x.invalid")),
        anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x.invalid")),
    ],
)
def test_api_error_is_infrastructure_failure(env, error, monkeypatch, tmp_path):
    FakeClient.error = error

    assert run_main(env) == 0

    assert "VERDICT: DID_NOT_RUN" in verdict_file(env)
    assert "infrastructure_failure=true" in outputs(env)
    assert "verdict=DID_NOT_RUN" in parse_verdict(env, monkeypatch, tmp_path)


def test_api_error_never_leaks_the_key(env, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", env["ANTHROPIC_API_KEY"])
    exc = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x.invalid"))
    exc.args = ("connection failed for sk-ant-test-value",)
    FakeClient.error = exc

    assert run_main(env) == 0

    assert "sk-ant-test-value" not in verdict_file(env)
    assert "sk-ant-test-value" not in outputs(env)


@pytest.mark.parametrize(
    "reply",
    [SimpleNamespace(content=[]), SimpleNamespace(content=None), text_reply("  \n")],
)
def test_empty_reply_is_infrastructure_failure(env, reply):
    FakeClient.reply = reply

    assert run_main(env) == 0

    assert "VERDICT: DID_NOT_RUN" in verdict_file(env)
    assert "infrastructure_failure=true" in outputs(env)


def test_reply_without_verdict_line_parses_as_blocking_needs_review(env, monkeypatch, tmp_path):
    FakeClient.reply = text_reply("I could not decide.")

    assert run_main(env) == 0

    assert "infrastructure_failure=false" in outputs(env)
    assert "verdict=NEEDS_REVIEW" in parse_verdict(env, monkeypatch, tmp_path)


def test_non_text_blocks_are_skipped():
    reply = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", text="x"),
            SimpleNamespace(type="text", text="ok"),
        ]
    )
    assert claude.extract_text(reply) == "ok"


def test_empty_context_file_fails_closed(env, tmp_path):
    Path(env["CONTEXT_FILE"]).write_text("  ", encoding="utf-8")
    assert run_main(env) == 0
    assert "context file is missing or empty" in verdict_file(env)
    assert FakeClient.last_kwargs is None


def test_missing_context_file_fails_closed(env):
    del env["CONTEXT_FILE"]
    assert run_main(env) == 0
    assert "infrastructure_failure=true" in outputs(env)


@pytest.mark.parametrize("agent", ["", "../x", "a/b", ".hidden", "a\\b"])
def test_load_system_prompt_rejects_unsafe_agent_names(tmp_path, agent):
    (tmp_path / "x.md").write_text("secret", encoding="utf-8")
    assert claude.load_system_prompt(agent, tmp_path) == ""


def test_stale_output_file_is_cleared_before_run(env):
    Path(env["AI_REVIEW_OUTPUT_FILE"]).write_text("VERDICT: PASS\n", encoding="utf-8")
    FakeClient.error = anthropic.APIConnectionError(
        request=httpx2.Request("POST", "https://x.invalid")
    )
    run_main(env)
    assert "VERDICT: PASS" not in verdict_file(env)


def test_stale_output_unlink_failure_is_config_error(env, monkeypatch, capsys):
    def boom(self, missing_ok=False):
        raise OSError("denied")

    monkeypatch.setattr(Path, "unlink", boom)
    assert run_main(env) == 2
    assert "cannot clear stale" in capsys.readouterr().err


def test_main_rejects_arguments(capsys):
    assert claude.main(["--x"]) == 2


def test_main_reports_bad_config(monkeypatch, capsys):
    monkeypatch.delenv("AI_REVIEW_OUTPUT_FILE", raising=False)
    assert claude.main([]) == 2
    assert "AI_REVIEW_OUTPUT_FILE is required" in capsys.readouterr().err


def test_main_runs_end_to_end(env, monkeypatch):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert claude.main([]) == 0
    assert "VERDICT: PASS" in verdict_file(env)



_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_spec_workflow_uses_claude_and_drops_copilot_token():
    workflow = (_REPO_ROOT / ".github/workflows/ai-spec-validation.yml").read_text(
        encoding="utf-8"
    )

    assert "COPILOT_GITHUB_TOKEN" not in workflow
    assert workflow.count("provider: claude") == 2
    assert workflow.count("anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}") == 2


def test_action_defaults_to_copilot_so_other_workflows_are_unchanged():
    action = (_REPO_ROOT / ".github/actions/ai-review/action.yml").read_text(encoding="utf-8")

    assert "provider:\n    description: |" in action
    assert "default: 'copilot'" in action
    assert "if: inputs.provider != 'claude' && steps.infra_gate.outputs.skip != 'true'" in action
