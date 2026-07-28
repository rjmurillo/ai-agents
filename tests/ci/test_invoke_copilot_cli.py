from __future__ import annotations

from collections.abc import Sequence

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
    assert calls[0][:3] == ("timeout", "120", "copilot")
    assert result.infrastructure_failure is True
    assert result.retry_count == 2
    assert "VERDICT: CRITICAL_FAIL" in result.output
    assert "after 3 attempts" in result.output


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
