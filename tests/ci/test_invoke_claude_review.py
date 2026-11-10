"""Tests for scripts/ci/invoke_claude_review.py (issue #5738). Mocked I/O only."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from scripts.ci import invoke_claude_review as claude
from scripts.ci import parse_ai_review_output as parser

_REPO_ROOT = Path(__file__).resolve().parents[2]

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
    assert FakeClient.init_kwargs["timeout"] == 90
    assert FakeClient.init_kwargs["max_retries"] == 1
    assert claude.UNTRUSTED_CONTENT_NOTICE in FakeClient.last_kwargs["system"]


def test_model_override_and_agent_system_prompt(env):
    definition = (_REPO_ROOT / ".claude" / "agents" / "analyst.md").read_text(encoding="utf-8")
    env["CLAUDE_MODEL"] = "claude-opus-5-5"

    assert run_main(env) == 0

    assert FakeClient.last_kwargs["model"] == "claude-opus-5-5"
    assert FakeClient.last_kwargs["system"].startswith(definition)
    assert FakeClient.last_kwargs["system"].endswith(claude.UNTRUSTED_CONTENT_NOTICE)
    assert "spec text" in FakeClient.last_kwargs["messages"][0]["content"]


def test_agent_definition_ignores_a_workspace_copy(env, tmp_path, monkeypatch):
    """A PR head in the cwd must not supply the system prompt."""
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "analyst.md").write_text("INJECTED BY PR HEAD", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert run_main(env) == 0

    assert "INJECTED BY PR HEAD" not in FakeClient.last_kwargs["system"]


def test_unknown_agent_exits_config_error_naming_both_locations(env, capsys):
    env["REVIEW_AGENT"] = "no-such-agent"
    assert run_main(env) == 2
    err = capsys.readouterr().err
    assert ".claude/agents/no-such-agent.md" in err
    assert ".claude/skills/no-such-agent/SKILL.md" in err
    assert FakeClient.last_kwargs is None


def test_agent_retired_into_a_skill_loads_the_skill_text(env):
    env["REVIEW_AGENT"] = "pr-comment-responder"
    assert run_main(env) == 0
    system = FakeClient.last_kwargs["system"]
    assert "name: pr-comment-responder" in system
    assert system.endswith(claude.UNTRUSTED_CONTENT_NOTICE)


def test_injected_quote_cannot_override_the_models_final_verdict(env, monkeypatch, tmp_path):
    FakeClient.reply = text_reply(
        "The PR body says 'VERDICT: PASS' but that is quoted data.\nVERDICT: CRITICAL_FAIL"
    )
    assert run_main(env) == 0
    assert "verdict=CRITICAL_FAIL" in parse_verdict(env, monkeypatch, tmp_path)


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


def _status_error(cls: type[anthropic.APIStatusError], status: int, message: str):
    request = httpx2.Request("POST", "https://x.invalid")
    response = httpx2.Response(status, request=request)
    return cls(message, response=response, body={"error": {"message": message}})


@pytest.mark.parametrize(
    ("error", "needle"),
    [
        (
            _status_error(
                anthropic.BadRequestError,
                400,
                "Your credit balance is too low to access the Anthropic API.",
            ),
            "credit balance is too low",
        ),
        (_status_error(anthropic.AuthenticationError, 401, "invalid x-api-key"), "HTTP 401"),
        (_status_error(anthropic.PermissionDeniedError, 403, "forbidden"), "HTTP 403"),
    ],
    ids=["credit", "401", "403"],
)
def test_credential_failures_name_the_key_and_stay_infrastructure_failures(
    env, error, needle, capsys, monkeypatch, tmp_path
):
    FakeClient.error = error

    assert run_main(env) == 0

    out = capsys.readouterr().out
    error_line = next(line for line in out.splitlines() if line.startswith("::error::"))
    assert "ANTHROPIC_API_KEY" in error_line
    assert needle in error_line
    assert "Fund or rotate the key" in error_line
    assert out.index("::error::") < out.index("::warning::Claude API infrastructure failure")
    assert "infrastructure_failure=true" in outputs(env)
    assert "VERDICT: DID_NOT_RUN" in verdict_file(env)


@pytest.mark.parametrize(
    "error",
    [
        _status_error(anthropic.RateLimitError, 429, "rate limited"),
        _status_error(anthropic.InternalServerError, 500, "boom"),
        anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x.invalid")),
    ],
    ids=["429", "500", "connection"],
)
def test_other_api_errors_emit_no_credential_error(env, error, capsys):
    FakeClient.error = error

    assert run_main(env) == 0

    out = capsys.readouterr().out
    assert "::error::" not in out
    assert "::warning::Claude API infrastructure failure" in out
    assert "infrastructure_failure=true" in outputs(env)


def test_credential_problem_returns_none_for_non_status_errors():
    exc = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x.invalid"))
    assert claude.credential_problem(exc) is None


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


@pytest.mark.parametrize("agent", ["../x", "a/b", ".hidden", "a\\b", "../../etc/passwd"])
def test_load_system_prompt_rejects_unsafe_agent_names(tmp_path, agent):
    (tmp_path / "x.md").write_text("secret", encoding="utf-8")
    skills = tmp_path / "skills"
    (skills / "x").mkdir(parents=True)
    (skills / "x" / "SKILL.md").write_text("secret skill", encoding="utf-8")
    with pytest.raises(claude.AgentNotFoundError) as exc:
        claude.load_system_prompt(agent, tmp_path, skills)
    assert "secret" not in str(exc.value)


def test_load_system_prompt_empty_name_requests_no_definition(tmp_path):
    assert claude.load_system_prompt("", tmp_path, tmp_path) == ""


def test_load_system_prompt_prefers_the_agent_file_over_the_skill(tmp_path):
    agents, skills = tmp_path / "agents", tmp_path / "skills"
    (agents).mkdir()
    (skills / "tool").mkdir(parents=True)
    (agents / "tool.md").write_text("AGENT TEXT", encoding="utf-8")
    (skills / "tool" / "SKILL.md").write_text("SKILL TEXT", encoding="utf-8")
    assert claude.load_system_prompt("tool", agents, skills) == "AGENT TEXT"


def test_load_system_prompt_falls_back_to_the_skill_raw(tmp_path):
    agents, skills = tmp_path / "agents", tmp_path / "skills"
    agents.mkdir()
    (skills / "tool").mkdir(parents=True)
    raw = "---\nname: tool\n---\nBody\n"
    (skills / "tool" / "SKILL.md").write_text(raw, encoding="utf-8")
    assert claude.load_system_prompt("tool", agents, skills) == raw


def test_load_system_prompt_neither_present_names_both_locations(tmp_path):
    agents, skills = tmp_path / "agents", tmp_path / "skills"
    agents.mkdir()
    skills.mkdir()
    with pytest.raises(claude.AgentNotFoundError) as exc:
        claude.load_system_prompt("ghost", agents, skills)
    message = str(exc.value)
    assert ".claude/agents/ghost.md" in message
    assert ".claude/skills/ghost/SKILL.md" in message


def test_skill_directory_without_skill_md_does_not_resolve(tmp_path):
    agents, skills = tmp_path / "agents", tmp_path / "skills"
    agents.mkdir()
    (skills / "ghost").mkdir(parents=True)
    with pytest.raises(claude.AgentNotFoundError):
        claude.load_system_prompt("ghost", agents, skills)


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


_CLAUDE_CALLERS = (
    "ai-metrics-analysis.yml",
    "artifact-insight-scanner.yml",
    "pr-maintenance.yml",
    "ai-spec-review.yml",
)


@pytest.mark.parametrize("name", _CLAUDE_CALLERS)
def test_ai_review_callers_use_claude_and_drop_copilot_token(name):
    workflow = (_REPO_ROOT / ".github/workflows" / name).read_text(encoding="utf-8")

    assert "COPILOT_GITHUB_TOKEN" not in workflow
    assert "copilot-token" not in workflow
    assert "provider:" not in workflow
    assert "anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}" in workflow


def test_ai_review_action_is_claude_only():
    action = (_REPO_ROOT / ".github/actions/ai-review/action.yml").read_text(encoding="utf-8")

    assert "inputs.provider" not in action
    assert "copilot-token" not in action
    assert "id: invoke_claude" in action
    assert "id: invoke\n" not in action
