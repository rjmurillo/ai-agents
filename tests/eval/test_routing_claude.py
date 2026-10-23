"""Claude Code backend for the routing benchmark (issue #5426). No real claude process starts.

The argv and environment builders are checked by value. The stream parser is checked against
reduced captures from claude 2.1.309 (2026-10-23) under
`tests/eval/fixtures/harness_capability/claude-2.1.309/`, plus one clearly synthetic
usage-limit stream. A fake runner stands in for the process, so these tests do not prove
a real claude run behaves this way; the committed probe doc and fixtures are that evidence.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.eval._routing_runner_test_support import (
    BOUNDED,
    claude_mod,
    config_dict,
    dag_mod,
    live_mod,
    parse,
    result_mod,
    scenarios,
)

FIXTURES = Path(__file__).parent / "fixtures" / "harness_capability" / "claude-2.1.309"

BILLING_ENV = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)


def _stream(name: str) -> str:
    return (FIXTURES / f"{name}.stdout.jsonl").read_text(encoding="utf-8")


def _mutate(name: str, edit: Any) -> str:
    """The named fixture with `edit(event)` applied to every event, as JSONL."""
    events = [json.loads(line) for line in _stream(name).splitlines()]
    for event in events:
        edit(event)
    return "".join(json.dumps(event) + "\n" for event in events)


def _scenario() -> Any:
    return next(s for s in scenarios() if s.scenario_id == BOUNDED)


class StreamRunner:
    """Returns a fixed stream, and records the call."""

    def __init__(self, stdout: str, *, returncode: int = 0, stderr: str = "") -> None:
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.calls: list[dict[str, Any]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append({"argv": argv, **kwargs})
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def _invoke(runner: StreamRunner) -> Any:
    scenario = _scenario()
    config = parse(config_dict())
    request = dag_mod.build_requests(config.strategy_for("E", "codex"), scenario)[0]
    with live_mod.LiveBackend("claude", runner=runner, real_home=True) as backend:
        return backend.invoke(request, scenario)


# --- argv ---------------------------------------------------------------------


def test_argv_carries_model_and_effort_in_the_flag_shapes_claude_documents() -> None:
    argv = claude_mod.claude_routing_argv("claude-haiku-5-5", "high", "PROMPT")

    assert argv[:3] == ["claude", "-p", "PROMPT"]
    assert argv[argv.index("--model") + 1] == "claude-haiku-5-5"
    assert argv[argv.index("--effort") + 1] == "high"
    assert argv[argv.index("--output-format") + 1] == "stream-json" and "--verbose" in argv


def test_argv_is_a_shell_free_list_of_strings() -> None:
    argv = claude_mod.claude_routing_argv("claude-opus-5-5", "low", "multi word; echo hi")

    assert all(isinstance(token, str) for token in argv)
    assert argv[2] == "multi word; echo hi"


def test_argv_confines_file_tools_and_limits_bash_to_python() -> None:
    argv = claude_mod.claude_routing_argv("claude-opus-5-5", "low", "PROMPT")
    allowed = argv[argv.index("--allowedTools") + 1 : argv.index("--permission-prompts")]

    assert "--restricted" in argv
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert argv[argv.index("--permission-prompts") + 1] == "none"
    assert "bypassPermissions" not in argv and "--dangerously-skip-permissions" not in argv
    assert [t for t in allowed if t.startswith("Bash")] == ["Bash(python:*)", "Bash(python3:*)"]


def test_argv_has_no_agent_tool_so_every_process_is_a_single_agent() -> None:
    argv = claude_mod.claude_routing_argv("claude-opus-5-5", "low", "PROMPT")
    tools = argv[argv.index("--tools") + 1].split(",")

    assert "Agent" not in tools and "Task" not in tools
    assert tools == ["Read", "Edit", "Write", "Glob", "Grep", "Bash"]


def test_argv_drops_ambient_context_sources() -> None:
    argv = claude_mod.claude_routing_argv("claude-opus-5-5", "low", "PROMPT")

    assert argv[argv.index("--setting-sources") + 1] == ""
    for flag in ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence"):
        assert flag in argv


@pytest.mark.parametrize("prompt", ["", "-p injected", "--model evil"])
def test_argv_refuses_a_prompt_that_is_empty_or_parses_as_an_option(prompt: str) -> None:
    with pytest.raises(ValueError, match="prompt"):
        claude_mod.claude_routing_argv("claude-opus-5-5", "low", prompt)


@pytest.mark.parametrize("effort", ["ultra", "", "High", "minimal"])
def test_argv_refuses_an_effort_the_cli_would_silently_ignore(effort: str) -> None:
    with pytest.raises(ValueError, match="effort"):
        claude_mod.claude_routing_argv("claude-opus-5-5", effort, "PROMPT")


@pytest.mark.parametrize("effort", claude_mod.CLAUDE_EFFORTS)
def test_argv_accepts_every_effort_the_cli_documents(effort: str) -> None:
    argv = claude_mod.claude_routing_argv("claude-opus-5-5", effort, "PROMPT")

    assert argv[argv.index("--effort") + 1] == effort


def test_live_argv_dispatches_claude_to_the_adapter() -> None:
    assert live_mod.live_argv("claude", "claude-haiku-5-5", "low", "P") == (
        claude_mod.claude_routing_argv("claude-haiku-5-5", "low", "P")
    )


# --- environment: the subscription is the only billing path ---------------------


@pytest.mark.parametrize("name", [*BILLING_ENV, "CLAUDE_CODE_OAUTH_TOKEN"])
def test_env_removes_every_api_billing_and_provider_switch(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, "must-not-pass")

    assert name not in claude_mod.claude_routing_env()


def test_env_keeps_home_for_the_stored_login_and_nothing_unrelated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", "/home/operator")
    monkeypatch.setenv("UNRELATED_SECRET", "must-not-pass")
    monkeypatch.setenv("CLAUDE_CODE_SUBAGENT_MODEL", "must-not-pass")

    env = claude_mod.claude_routing_env()

    assert env["HOME"] == "/home/operator"
    assert "UNRELATED_SECRET" not in env and "CLAUDE_CODE_SUBAGENT_MODEL" not in env


def test_env_turns_off_instruction_discovery_and_autoupdate() -> None:
    env = claude_mod.claude_routing_env()

    assert env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1"
    assert env["DISABLE_AUTOUPDATER"] == "1"


def test_the_backend_hands_the_process_a_billing_free_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in BILLING_ENV:
        monkeypatch.setenv(name, "must-not-pass")
    runner = StreamRunner(_stream("plan-writer"))

    _invoke(runner)

    env = runner.calls[0]["env"]
    assert not set(BILLING_ENV) & set(env)
    assert runner.calls[0]["stdin"] == subprocess.DEVNULL and "shell" not in runner.calls[0]


# --- gate -----------------------------------------------------------------------


def test_claude_is_refused_without_real_home_even_with_an_api_key() -> None:
    with pytest.raises(live_mod.LiveGateError, match="claude.*--real-home"):
        live_mod.require_live_authorization(["claude"], {"ANTHROPIC_API_KEY": "key"})


def test_real_home_opens_the_gate_for_claude() -> None:
    live_mod.require_live_authorization(["claude"], {}, real_home=True)


def test_the_backend_refuses_claude_without_real_home() -> None:
    with pytest.raises(live_mod.LiveGateError, match="real_home"):
        live_mod.LiveBackend("claude")


def test_claude_credential_names_come_from_the_runtime_allowlist() -> None:
    assert live_mod.credential_names("claude") == ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")


# --- parser on recorded streams ----------------------------------------------------


def test_a_completed_subscription_run_yields_model_version_and_uncached_tokens() -> None:
    facts = claude_mod.parse_claude_run(_stream("plan-writer"))

    assert facts.completed and facts.failure == ""
    assert facts.models == ("claude-opus-5-5",)
    assert (facts.cli_version, facts.api_key_source) == ("2.1.309", "none")
    # usage: input_tokens 4 + cache_creation_input_tokens 1313, cache_read 13030, output 204.
    assert (facts.input_tokens, facts.cache_read_tokens, facts.output_tokens) == (1317, 13030, 204)


def test_cache_reads_are_reported_apart_and_never_added_to_input() -> None:
    facts = claude_mod.parse_claude_run(_stream("fresh-reader"))

    assert facts.cache_read_tokens == 13057 and facts.input_tokens == 1311


def test_a_run_names_no_effort_so_none_is_ever_observed() -> None:
    assert not hasattr(claude_mod.parse_claude_run(_stream("effort-max")), "efforts")
    assert '"effort"' not in _stream("effort-max")


def test_a_synthetic_error_message_is_not_an_observed_model() -> None:
    facts = claude_mod.parse_claude_run(_stream("invalid-model"))

    assert facts.models == ()


def test_the_invalid_model_error_text_reaches_the_failure() -> None:
    facts = claude_mod.parse_claude_run(_stream("invalid-model"))

    assert not facts.completed
    assert "api_error_status=404" in facts.failure
    assert "There's an issue with the selected model (claude-nonexistent-9-9)" in facts.failure


def test_the_usage_limit_text_reaches_the_failure() -> None:
    events = [json.loads(line) for line in _stream("usage-limit.synthetic").splitlines()]
    assert events[0]["subtype"] == "synthetic_fixture" and "SYNTHETIC" in events[0]["note"]

    facts = claude_mod.parse_claude_run(_stream("usage-limit.synthetic"))

    assert not facts.completed
    assert "api_error_status=429" in facts.failure
    assert "You've hit your usage limit. Your limit resets at 3pm." in facts.failure


def test_an_ignored_effort_warning_fails_a_run_that_exited_zero() -> None:
    stderr = (FIXTURES / "effort-ultra-ignored.stderr.txt").read_text(encoding="utf-8")

    facts = claude_mod.parse_claude_run(_stream("effort-ultra-ignored"), stderr)

    assert not facts.completed
    assert facts.failure.startswith("effort not applied: Warning: Unknown --effort value 'ultra'")


def test_the_same_stream_without_the_warning_completes() -> None:
    assert claude_mod.parse_claude_run(_stream("effort-ultra-ignored")).completed


def test_an_empty_stream_fails_and_carries_stderr() -> None:
    facts = claude_mod.parse_claude_run("", "[claude-code:crash] boom")

    assert not facts.completed
    assert facts.failure == "no result event in stream: [claude-code:crash] boom"


def test_a_stream_with_no_result_and_no_stderr_still_fails() -> None:
    truncated = "".join(_stream("plan-writer").splitlines(keepends=True)[:-1])

    facts = claude_mod.parse_claude_run(truncated)

    assert not facts.completed and facts.failure == "no result event in stream"


def test_garbage_lines_are_skipped_not_fatal() -> None:
    facts = claude_mod.parse_claude_run("not json\n[1,2]\n" + _stream("plan-writer"))

    assert facts.completed and facts.models == ("claude-opus-5-5",)


def _set_key_source(value: Any) -> Any:
    def edit(event: dict[str, Any]) -> None:
        if event.get("subtype") == "init":
            event["apiKeySource"] = value

    return edit


@pytest.mark.parametrize("source", ["ANTHROPIC_API_KEY", "/login/managed", ""])
def test_a_run_that_did_not_bill_the_subscription_is_a_harness_failure(source: str) -> None:
    facts = claude_mod.parse_claude_run(_mutate("plan-writer", _set_key_source(source)))

    assert not facts.completed
    assert facts.failure.startswith("billing guard:") and repr(source) in facts.failure


def test_a_run_with_no_init_event_cannot_confirm_the_billing_path() -> None:
    lines = [line for line in _stream("plan-writer").splitlines() if '"subtype":"init"' not in line]

    facts = claude_mod.parse_claude_run("\n".join(lines))

    assert not facts.completed and facts.failure.startswith("billing guard:")
    assert facts.api_key_source is None


def test_a_non_success_result_subtype_is_a_failure() -> None:
    def edit(event: dict[str, Any]) -> None:
        if event["type"] == "result":
            event["subtype"] = "error_max_turns"

    facts = claude_mod.parse_claude_run(_mutate("plan-writer", edit))

    assert not facts.completed and facts.failure == "result subtype error_max_turns"


def test_a_stream_with_two_results_reads_the_last_cumulative_one() -> None:
    first = json.loads(_stream("plan-writer").splitlines()[-1])
    first["usage"] = {**first["usage"], "output_tokens": 1}

    facts = claude_mod.parse_claude_run(json.dumps(first) + "\n" + _stream("plan-writer"))

    assert facts.output_tokens == 204


def test_a_malformed_usage_block_counts_zero_not_a_crash() -> None:
    def edit(event: dict[str, Any]) -> None:
        if event["type"] == "result":
            event["usage"] = ["bad"]

    facts = claude_mod.parse_claude_run(_mutate("plan-writer", edit))

    assert facts.completed and facts.input_tokens == facts.output_tokens == 0


def test_error_text_is_one_capped_line_without_control_characters() -> None:
    cleaned = claude_mod.clean_detail("line one\n\x1b[31mred\x00\r\nline  two")

    assert cleaned == "line one [31mred line two"
    long = claude_mod.clean_detail("x" * 600)
    assert len(long) == 503 and long.endswith("...")


# --- the backend, end to end over a fake process ------------------------------------


def test_a_completed_run_is_backend_evidence_for_the_model_and_never_for_effort() -> None:
    runner = StreamRunner(_stream("plan-writer"))

    observation = _invoke(runner)

    assert observation.observed_model == "claude-opus-5-5"
    assert observation.observed_effort is None
    assert observation.evidence is result_mod.EvidenceKind.BACKEND
    assert (observation.input_tokens, observation.output_tokens) == (1317, 204)
    assert observation.failure is None
    assert observation.tool_sandbox == claude_mod.CLAUDE_SANDBOX_LABEL
    assert (
        result_mod.value_verdict("low", None, observation.evidence) is result_mod.Verdict.UNVERIFIED
    )


def test_a_requested_model_the_backend_did_not_serve_is_a_mismatch() -> None:
    observation = _invoke(StreamRunner(_stream("plan-writer")))

    verdict = result_mod.value_verdict(
        "claude-haiku-5-5", observation.observed_model, observation.evidence
    )

    assert verdict is result_mod.Verdict.MISMATCH


def test_a_cli_error_surfaces_its_text_and_not_only_the_exit_code() -> None:
    runner = StreamRunner(_stream("invalid-model"), returncode=1)

    observation = _invoke(runner)

    assert observation.failure is result_mod.FailureKind.HARNESS
    assert "exit code 1" in observation.failure_detail
    assert "There's an issue with the selected model" in observation.failure_detail
    assert observation.observed_model is None
    assert observation.evidence is result_mod.EvidenceKind.NONE
    assert (observation.input_tokens, observation.output_tokens) == (None, None)


def test_a_usage_limit_stops_the_row_as_a_harness_failure_with_the_limit_text() -> None:
    runner = StreamRunner(_stream("usage-limit.synthetic"), returncode=1)

    observation = _invoke(runner)

    assert observation.failure is result_mod.FailureKind.HARNESS
    assert "usage limit" in observation.failure_detail


def test_an_api_billed_stream_is_a_harness_failure_even_with_exit_zero() -> None:
    runner = StreamRunner(_mutate("plan-writer", _set_key_source("ANTHROPIC_API_KEY")))

    observation = _invoke(runner)

    assert observation.failure is result_mod.FailureKind.HARNESS
    assert "billing guard" in observation.failure_detail
    assert (observation.input_tokens, observation.output_tokens) == (None, None)


def test_a_crash_with_only_stderr_surfaces_the_stderr() -> None:
    runner = StreamRunner("", returncode=137, stderr="killed by signal")

    observation = _invoke(runner)

    assert "exit code 137" in observation.failure_detail
    assert "killed by signal" in observation.failure_detail
