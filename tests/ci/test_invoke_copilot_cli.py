from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from scripts.ci import invoke_copilot_cli as invoke


def make_config(tmp_path, context_file=None) -> invoke.InvokeConfig:
    return invoke.InvokeConfig(
        ai_review_output_file=tmp_path / "ai-review-output.txt",
        github_output_file=tmp_path / "github-output.txt",
        additional_context="extra facts",
        timeout_minutes=2,
        copilot_agent="reviewer",
        copilot_model="gpt-5",
        context_mode="full",
        context_file=context_file,
    )


def test_build_full_prompt_combines_mode_template_context_and_extra(tmp_path):
    prompt_template = tmp_path / "prompt.md"
    prompt_template.write_text("Review this.", encoding="utf-8")
    context_file = tmp_path / "context.md"
    context_file.write_text("diff content", encoding="utf-8")

    prompt = invoke.build_full_prompt(
        context_mode="full",
        additional_context="extra facts",
        context_file=context_file,
        prompt_template_path=prompt_template,
    )

    assert prompt.startswith("CONTEXT_MODE: full\n\nReview this.")
    assert "## Context\n\ndiff content" in prompt
    assert "## Additional Context\n\nextra facts" in prompt


def test_invoke_with_retry_converts_repeated_infra_failure_to_verdict(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str]) -> invoke.CommandResult:
        calls.append(tuple(argv))
        return invoke.CommandResult(124, "", "")

    result = invoke.invoke_with_retry(
        config=make_config(tmp_path),
        full_prompt="prompt",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    assert len(calls) == 3
    assert calls[0][:4] == ("timeout", "--kill-after=5s", "120", "copilot")
    assert result.infrastructure_failure is True
    assert result.retry_count == 2
    assert "VERDICT: CRITICAL_FAIL" in result.output
    assert "after 3 attempts" in result.output


def test_invoke_caps_timeout_to_preserve_finalization_reserve(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str]) -> invoke.CommandResult:
        calls.append(tuple(argv))
        return invoke.CommandResult(0, "VERDICT: PASS", "")

    config = replace(make_config(tmp_path), action_deadline_epoch=200.0)
    result = invoke.invoke_with_retry(
        config=config,
        full_prompt="prompt",
        runner=runner,
        clock=lambda: 100.0,
    )

    assert calls[0][:4] == ("timeout", "--kill-after=5s", "35", "copilot")
    assert result.infrastructure_failure is False


def test_invoke_fails_closed_when_finalization_window_has_started(tmp_path):
    calls: list[tuple[str, ...]] = []
    config = replace(make_config(tmp_path), action_deadline_epoch=160.0)

    result = invoke.invoke_with_retry(
        config=config,
        full_prompt="prompt",
        runner=lambda argv: calls.append(tuple(argv)) or invoke.CommandResult(0, "", ""),
        clock=lambda: 100.0,
    )

    assert calls == []
    assert result.exit_code == 124
    assert result.infrastructure_failure is True
    assert "budget was exhausted" in result.output


def test_invoke_does_not_retry_permanent_auth_rejection(tmp_path):
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str]) -> invoke.CommandResult:
        calls.append(tuple(argv))
        return invoke.CommandResult(1, "", "HTTP 401: Bad credentials")

    result = invoke.invoke_with_retry(
        config=make_config(tmp_path),
        full_prompt="prompt",
        runner=runner,
        sleeper=lambda _seconds: None,
    )

    assert len(calls) == 1
    assert result.infrastructure_failure is True
    assert result.retry_count == 0
    assert result.output.startswith("VERDICT: DID_NOT_RUN")


def test_invoke_honors_retry_after_for_http_429(tmp_path):
    sleeps: list[int] = []
    responses = iter(
        [
            invoke.CommandResult(
                1,
                "",
                "HTTP 429: Too Many Requests\nRetry-After: 7",
            ),
            invoke.CommandResult(0, "VERDICT: PASS", ""),
        ]
    )

    result = invoke.invoke_with_retry(
        config=make_config(tmp_path),
        full_prompt="prompt",
        runner=lambda _argv: next(responses),
        sleeper=sleeps.append,
    )

    assert sleeps == [7]
    assert result.infrastructure_failure is False
    assert result.retry_count == 1


def test_write_results_redacts_secrets(tmp_path, monkeypatch):
    secret = "ghp_super_secret_value"
    monkeypatch.setenv("COPILOT_GITHUB_TOKEN", secret)
    config = make_config(tmp_path)
    result = invoke.AttemptResult(
        exit_code=1,
        output=f"token={secret}",
        stderr=f"Authorization: Bearer {secret}",
        infrastructure_failure=True,
        retry_count=0,
    )

    invoke.write_results(config, f"prompt {secret}", result)

    persisted = config.ai_review_output_file.read_text(
        encoding="utf-8"
    ) + config.github_output_file.read_text(encoding="utf-8")
    assert secret not in persisted
    assert "***" in persisted


def test_write_results_redacts_uninstalled_github_token_shape(tmp_path, monkeypatch):
    token = f"ghp_{'A' * 36}"
    for variable in invoke.SECRET_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    config = make_config(tmp_path)
    result = invoke.AttemptResult(
        exit_code=1,
        output=f"cached token={token}",
        stderr="",
        infrastructure_failure=True,
        retry_count=0,
    )

    invoke.write_results(config, "prompt", result)

    persisted = config.ai_review_output_file.read_text(
        encoding="utf-8"
    ) + config.github_output_file.read_text(encoding="utf-8")
    assert token not in persisted
    assert "[redacted: github-token]" in persisted


def test_run_fails_closed_for_empty_context_file(tmp_path):
    context_file = tmp_path / "context.md"
    context_file.write_text(" \n", encoding="utf-8")
    config = make_config(tmp_path, context_file)

    assert invoke.run(config) == invoke.EXIT_OK

    assert config.ai_review_output_file.read_text(encoding="utf-8").startswith(
        "VERDICT: DID_NOT_RUN"
    )
    assert "infrastructure_failure=true" in config.github_output_file.read_text(encoding="utf-8")


def test_run_redacts_prompt_before_invocation(tmp_path, monkeypatch):
    token = f"ghp_{'A' * 36}"
    context_file = tmp_path / "context.md"
    context_file.write_text(f"credential={token}", encoding="utf-8")
    config = make_config(tmp_path, context_file)
    observed: list[str] = []
    monkeypatch.setattr(invoke, "FULL_PROMPT_PATH", tmp_path / "full-prompt.md")

    def fake_invoke_with_retry(*, config, full_prompt, **_kwargs):
        del config
        observed.append(full_prompt)
        return invoke.AttemptResult(0, "VERDICT: PASS", "", False, 0)

    monkeypatch.setattr(invoke, "invoke_with_retry", fake_invoke_with_retry)

    assert invoke.run(config) == invoke.EXIT_OK
    assert token not in observed[0]
    assert "[redacted: github-token]" in observed[0]


def test_write_results_preserves_outputs_and_flags(tmp_path):
    config = make_config(tmp_path)
    result = invoke.AttemptResult(
        exit_code=0,
        output="VERDICT: PASS",
        stderr="debug",
        infrastructure_failure=False,
        retry_count=1,
    )

    invoke.write_results(config, "full prompt", result)

    assert config.ai_review_output_file.read_text(encoding="utf-8") == "VERDICT: PASS\n"
    github_output = config.github_output_file.read_text(encoding="utf-8")
    assert "raw_output<<EOF_RAW\nVERDICT: PASS\nEOF_RAW" in github_output
    assert "stderr_output<<EOF_STDERR\ndebug\nEOF_STDERR" in github_output
    assert "full_prompt<<EOF_FULL_PROMPT\nfull prompt\nEOF_FULL_PROMPT" in github_output
    assert "copilot_exit_code=0" in github_output
    assert "infrastructure_failure=false" in github_output
    assert "retry_count=1" in github_output


def test_parse_config_rejects_invalid_timeout(tmp_path):
    env = {
        "AI_REVIEW_OUTPUT_FILE": str(tmp_path / "out.txt"),
        "GITHUB_OUTPUT": str(tmp_path / "github-output.txt"),
        "TIMEOUT_MINUTES": "abc",
    }

    try:
        invoke.parse_config(env)
    except ValueError as exc:
        assert str(exc) == "TIMEOUT_MINUTES must be an integer"
    else:
        raise AssertionError("parse_config should reject a non-integer timeout")


def test_run_command_catches_file_not_found_error():
    result = invoke.run_command(["__nonexistent_binary_xyz__"])

    assert result.returncode == 127
    assert "command not found" in result.stderr
    assert result.stdout == ""
