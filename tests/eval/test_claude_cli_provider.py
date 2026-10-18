"""Tests for the Claude Code CLI transport, the claude/subscription cell.

Offline: no CLI is launched, and the fixtures assert the two properties that
decide whether the cell measures what it claims, that the metered credentials
never reach the child and that an unattributed model never scores.
"""

from __future__ import annotations

import json

import pytest

from tests.eval._cli_transport_test_support import (
    MESSAGES,
    Recorder,
    _claude_cli,
    claude_payload,
    install_runner,
)
from tests.eval._credential_test_support import set_sources

# --- Claude Code CLI ----------------------------------------------------


@pytest.fixture
def claude_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-token")
    for name in _claude_cli._BLOCKED_BILLING_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_claude_cli_returns_the_result_field(
    claude_env: pytest.MonkeyPatch,
) -> None:
    install_runner(claude_env, Recorder(stdout=claude_payload()))

    answer = _claude_cli._ClaudeCLIProvider().complete(
        messages=MESSAGES, model="claude-haiku-4-5-20251001"
    )

    assert answer == "PONG"


def test_claude_cli_argv_disables_tools_mcp_and_ambient_settings(
    claude_env: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder(stdout=claude_payload())
    install_runner(claude_env, recorder)

    _claude_cli._ClaudeCLIProvider().complete(messages=MESSAGES, model="claude-haiku-4-5-20251001")

    argv = recorder.argv
    assert argv[:2] == ["claude", "--print"]
    assert "--output-format" in argv and argv[argv.index("--output-format") + 1] == "json"
    assert "--strict-mcp-config" in argv
    assert json.loads(argv[argv.index("--mcp-config") + 1]) == {"mcpServers": {}}
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert "mcp__*" in argv[argv.index("--disallowed-tools") + 1]
    assert "--disable-slash-commands" in argv
    assert "--no-session-persistence" in argv


def test_claude_cli_sends_the_prompt_on_stdin_not_in_argv(
    claude_env: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder(stdout=claude_payload())
    install_runner(claude_env, recorder)

    _claude_cli._ClaudeCLIProvider().complete(
        messages=[{"role": "user", "content": "SECRET-FIXTURE-MARKER"}],
        model="claude-haiku-4-5-20251001",
    )

    assert "SECRET-FIXTURE-MARKER" in recorder.calls[-1]["input"]
    assert not any("SECRET-FIXTURE-MARKER" in part for part in recorder.argv)


def test_claude_cli_strips_metered_credentials_from_the_child(
    claude_env: pytest.MonkeyPatch,
) -> None:
    """Without this the subscription cell silently bills the API account."""
    claude_env.setenv("ANTHROPIC_API_KEY", "sk-metered")
    claude_env.setenv("ANTHROPIC_AUTH_TOKEN", "metered-too")
    recorder = Recorder(stdout=claude_payload())
    install_runner(claude_env, recorder)

    _claude_cli._ClaudeCLIProvider().complete(messages=MESSAGES, model="claude-haiku-4-5-20251001")

    env = recorder.calls[-1]["env"]
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth-token"
    assert env["CLAUDE_CONFIG_DIR"]


def test_claude_cli_refuses_without_the_subscription_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    set_sources(monkeypatch, "_claude_cli", probe=False)
    recorder = Recorder(stdout=claude_payload())
    install_runner(monkeypatch, recorder)

    with pytest.raises(RuntimeError, match="CLAUDE_CODE_OAUTH_TOKEN"):
        _claude_cli._ClaudeCLIProvider().complete(
            messages=MESSAGES, model="claude-haiku-4-5-20251001"
        )

    assert recorder.calls == []


def test_claude_cli_records_the_resolved_model_as_the_fingerprint(
    claude_env: pytest.MonkeyPatch,
) -> None:
    install_runner(claude_env, Recorder(stdout=claude_payload()))
    provider = _claude_cli._ClaudeCLIProvider()

    provider.complete(messages=MESSAGES, model="claude-haiku-4-5")

    assert provider.system_fingerprint == "claude-haiku-4-5-20251001"


def test_claude_cli_accepts_an_alias_and_its_dated_id_together(
    claude_env: pytest.MonkeyPatch,
) -> None:
    """Measured shape: --model with an alias reports both keys."""
    payload = json.dumps(
        {
            "is_error": False,
            "result": "PONG",
            "modelUsage": {
                "claude-haiku-4-5-20251001": {},
                "claude-haiku-4-5": {},
            },
        }
    )
    install_runner(claude_env, Recorder(stdout=payload))
    provider = _claude_cli._ClaudeCLIProvider()

    provider.complete(messages=MESSAGES, model="claude-haiku-4-5")

    assert provider.system_fingerprint == "claude-haiku-4-5-20251001"


def test_claude_cli_refuses_a_reply_from_another_model(
    claude_env: pytest.MonkeyPatch,
) -> None:
    install_runner(claude_env, Recorder(stdout=claude_payload(model="claude-opus-5")))

    with pytest.raises(RuntimeError, match="model attribution mismatch"):
        _claude_cli._ClaudeCLIProvider().complete(messages=MESSAGES, model="claude-haiku-4-5")


def test_claude_cli_reports_no_fingerprint_when_usage_is_absent(
    claude_env: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"is_error": False, "result": "PONG"})
    install_runner(claude_env, Recorder(stdout=payload))
    provider = _claude_cli._ClaudeCLIProvider()

    provider.complete(messages=MESSAGES, model="claude-haiku-4-5")

    assert provider.system_fingerprint is None


@pytest.mark.parametrize(
    "stdout,expected",
    [
        ("not json at all", "not the JSON envelope"),
        ("[1, 2]", "not an object"),
        (json.dumps({"is_error": True, "subtype": "error_max_turns"}), "error result"),
        (json.dumps({"is_error": False, "result": "   "}), "no choices"),
        (json.dumps({"is_error": False}), "no choices"),
    ],
)
def test_claude_cli_refuses_an_unreadable_envelope(
    claude_env: pytest.MonkeyPatch, stdout: str, expected: str
) -> None:
    install_runner(claude_env, Recorder(stdout=stdout))

    with pytest.raises(RuntimeError, match=expected):
        _claude_cli._ClaudeCLIProvider().complete(messages=MESSAGES, model="claude-haiku-4-5")


def test_claude_cli_reports_a_nonzero_exit_without_leaking_stderr(
    claude_env: pytest.MonkeyPatch,
) -> None:
    install_runner(claude_env, Recorder(returncode=2, stderr="Invalid API key sk-leaked-value"))

    with pytest.raises(RuntimeError) as excinfo:
        _claude_cli._ClaudeCLIProvider().complete(messages=MESSAGES, model="claude-haiku-4-5")

    assert "sk-leaked-value" not in str(excinfo.value)
    assert "authentication failed" in str(excinfo.value)


def test_claude_cli_honors_an_executable_override(
    claude_env: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder(stdout=claude_payload())
    install_runner(claude_env, recorder)

    _claude_cli._ClaudeCLIProvider(executable="/opt/claude").complete(
        messages=MESSAGES, model="claude-haiku-4-5-20251001"
    )

    assert recorder.argv[0] == "/opt/claude"


# --- output tokens from the envelope usage record (#6683) ----------------


def test_claude_cli_records_output_tokens_from_the_usage_record(
    claude_env: pytest.MonkeyPatch,
) -> None:
    """Measured shape: thinking tokens ride inside `output_tokens`."""
    usage = {
        "input_tokens": 9,
        "output_tokens": 49,
        "output_tokens_details": {"thinking_tokens": 38},
    }
    install_runner(claude_env, Recorder(stdout=claude_payload(usage=usage)))
    provider = _claude_cli._ClaudeCLIProvider()

    provider.complete(messages=MESSAGES, model="claude-haiku-4-5")

    assert provider.output_tokens == 49


def test_claude_cli_accepts_a_zero_token_count(claude_env: pytest.MonkeyPatch) -> None:
    install_runner(claude_env, Recorder(stdout=claude_payload(usage={"output_tokens": 0})))
    provider = _claude_cli._ClaudeCLIProvider()

    provider.complete(messages=MESSAGES, model="claude-haiku-4-5")

    assert provider.output_tokens == 0


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        [],
        "49",
        {"input_tokens": 9},
        {"output_tokens": None},
        {"output_tokens": "49"},
        {"output_tokens": 49.5},
        {"output_tokens": True},
        {"output_tokens": -1},
    ],
)
def test_claude_cli_reports_no_token_count_when_the_usage_record_is_unusable(
    claude_env: pytest.MonkeyPatch, usage: object
) -> None:
    install_runner(claude_env, Recorder(stdout=claude_payload(usage=usage)))
    provider = _claude_cli._ClaudeCLIProvider()

    provider.complete(messages=MESSAGES, model="claude-haiku-4-5")

    assert provider.output_tokens is None


def test_claude_cli_clears_the_token_count_between_calls(
    claude_env: pytest.MonkeyPatch,
) -> None:
    provider = _claude_cli._ClaudeCLIProvider()
    install_runner(claude_env, Recorder(stdout=claude_payload(usage={"output_tokens": 7})))
    provider.complete(messages=MESSAGES, model="claude-haiku-4-5")
    assert provider.output_tokens == 7

    install_runner(claude_env, Recorder(returncode=2, stderr="boom"))
    with pytest.raises(RuntimeError):
        provider.complete(messages=MESSAGES, model="claude-haiku-4-5")

    assert provider.output_tokens is None


def test_claude_cli_clears_the_token_count_when_the_prompt_cannot_be_built(
    claude_env: pytest.MonkeyPatch,
) -> None:
    provider = _claude_cli._ClaudeCLIProvider()
    install_runner(claude_env, Recorder(stdout=claude_payload(usage={"output_tokens": 7})))
    provider.complete(messages=MESSAGES, model="claude-haiku-4-5")
    assert provider.output_tokens == 7

    with pytest.raises(RuntimeError, match="message role"):
        provider.complete(
            messages=[{"role": "assistant", "content": "x"}], model="claude-haiku-4-5"
        )

    assert provider.output_tokens is None
