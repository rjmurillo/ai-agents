"""Invoke Copilot CLI for the ai-review composite action."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
PROMPT_TEMPLATE_PATH = Path("/tmp/ai-review-prompt.md")
FULL_PROMPT_PATH = Path("/tmp/ai-review-full-prompt.md")
INFRASTRUCTURE_PATTERN = re.compile(
    r"(rate limit|timeout|network error|connection refused|connection reset|ECONNREFUSED|"
    r"ETIMEDOUT|503|502|504|No authentication|authentication failed|auth.*error|not available)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class InvokeConfig:
    ai_review_output_file: Path
    github_output_file: Path
    additional_context: str
    timeout_minutes: int
    copilot_agent: str
    copilot_model: str
    context_mode: str
    context_file: Path | None


@dataclass(frozen=True, slots=True)
class AttemptResult:
    exit_code: int
    output: str
    stderr: str
    infrastructure_failure: bool
    retry_count: int


def run_command(argv: Sequence[str]) -> CommandResult:
    completed = subprocess.run(list(argv), check=False, capture_output=True, text=True)
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")


def append_multiline_output(path: Path, name: str, value: str, delimiter: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{name}<<{delimiter}\n")
        handle.write(value)
        if value and not value.endswith("\n"):
            handle.write("\n")
        handle.write(f"{delimiter}\n")


def parse_config(env: Mapping[str, str]) -> InvokeConfig:
    output_file = env.get("AI_REVIEW_OUTPUT_FILE")
    github_output = env.get("GITHUB_OUTPUT")
    if not output_file:
        raise ValueError("AI_REVIEW_OUTPUT_FILE is required")
    if not github_output:
        raise ValueError("GITHUB_OUTPUT is required")

    timeout_text = env.get("TIMEOUT_MINUTES", "")
    try:
        timeout_minutes = int(timeout_text)
    except ValueError as exc:
        raise ValueError("TIMEOUT_MINUTES must be an integer") from exc
    if timeout_minutes < 0:
        raise ValueError("TIMEOUT_MINUTES must be >= 0")

    context_file_text = env.get("CONTEXT_FILE", "")
    context_file = Path(context_file_text) if context_file_text else None
    return InvokeConfig(
        ai_review_output_file=Path(output_file),
        github_output_file=Path(github_output),
        additional_context=env.get("ADDITIONAL_CONTEXT", ""),
        timeout_minutes=timeout_minutes,
        copilot_agent=env.get("COPILOT_AGENT", ""),
        copilot_model=env.get("COPILOT_MODEL", ""),
        context_mode=env.get("CONTEXT_MODE") or "summary",
        context_file=context_file,
    )


def build_full_prompt(
    *,
    context_mode: str,
    additional_context: str,
    context_file: Path | None,
    prompt_template_path: Path = PROMPT_TEMPLATE_PATH,
) -> str:
    prompt_parts = [f"CONTEXT_MODE: {context_mode}", ""]
    if prompt_template_path.is_file():
        prompt_parts.append(prompt_template_path.read_text(encoding="utf-8"))
        prompt_parts.append("")

    prompt_parts.extend(["## Context", ""])
    if context_file and context_file.is_file():
        prompt_parts.append(context_file.read_text(encoding="utf-8"))

    if additional_context:
        prompt_parts.extend(["", "## Additional Context", "", additional_context])
    return "\n".join(prompt_parts)


def is_infrastructure_failure(exit_code: int, output: str, stderr: str) -> bool:
    if exit_code == 124:
        return True
    if exit_code != 0 and not output and not stderr:
        return True
    return bool(stderr and "VERDICT:" not in output and INFRASTRUCTURE_PATTERN.search(stderr))


def invoke_with_retry(
    *,
    config: InvokeConfig,
    full_prompt: str,
    runner: Callable[[Sequence[str]], CommandResult] = run_command,
    sleeper: Callable[[int], None] = time.sleep,
    retry_delays: Sequence[int] = (0, 30, 60),
) -> AttemptResult:
    max_retries = 2
    attempt = 0
    retry_count = 0
    timeout_seconds = config.timeout_minutes * 60
    output = ""
    stderr = ""
    exit_code = 0
    infrastructure_failure = False

    while attempt <= max_retries:
        retry_delay = retry_delays[attempt]
        if attempt > 0:
            print()
            print(f"=== RETRY ATTEMPT {attempt}/{max_retries} ===")
            print(f"Infrastructure failure detected. Retrying in {retry_delay}s...")
            sleeper(retry_delay)

        print(
            "Invoking Copilot CLI "
            f"(attempt {attempt + 1}/{max_retries + 1}, timeout: {config.timeout_minutes}m)..."
        )
        print(f"Agent: {config.copilot_agent}, Model: {config.copilot_model}")
        print(f"Prompt size: {len(full_prompt.encode('utf-8'))} bytes")

        result = runner(
            [
                "timeout",
                str(timeout_seconds),
                "copilot",
                "--no-auto-update",
                "--no-color",
                "--silent",
                "--agent",
                config.copilot_agent,
                "--model",
                config.copilot_model,
                "--prompt",
                full_prompt,
            ]
        )
        exit_code = result.returncode
        output = result.stdout
        stderr = result.stderr

        print(f"Exit code: {exit_code}")
        print(f"Stdout length: {len(output)} chars")
        print(f"Stderr length: {len(stderr)} chars")

        if is_infrastructure_failure(exit_code, output, stderr):
            infrastructure_failure = True
            print(f"::warning::Infrastructure failure detected (exit code: {exit_code})")
            if stderr:
                print(f"::warning::stderr (truncated): {stderr[:500]}")
                if "rate limit" in stderr.lower():
                    print(
                        "::warning::Copilot may be rate limited. No public Copilot "
                        "rate-limit API is available; relying on CLI response and backoff."
                    )
            if attempt < max_retries:
                attempt += 1
                retry_count += 1
                continue

            total_attempts = attempt + 1
            output = (
                "VERDICT: CRITICAL_FAIL\n"
                "MESSAGE: Copilot CLI infrastructure failure after "
                f"{total_attempts} attempts (exit code {exit_code}). Check "
                "COPILOT_GITHUB_TOKEN scope, rate limits, or network connectivity."
            )
            if not stderr:
                stderr = "Infrastructure failure detected after retries."
            break

        infrastructure_failure = False
        break

    return AttemptResult(
        exit_code=exit_code,
        output=output,
        stderr=stderr,
        infrastructure_failure=infrastructure_failure,
        retry_count=retry_count,
    )


def analyze_non_infra_failure(result: AttemptResult) -> int:
    if result.infrastructure_failure or result.exit_code == 0:
        return EXIT_OK

    print(f"::error::Copilot CLI exited with code {result.exit_code}")
    if result.stderr:
        print("Stderr output:")
        print(result.stderr)

    if not result.output and not result.stderr:
        print()
        print("::error::=== NO OUTPUT - JOB FAILED ===")
        print("::error::Copilot CLI produced no output (stdout or stderr).")
        print("::error::")
        print("::error::LIKELY CAUSES:")
        print("::error::  1. MISSING COPILOT ACCESS - GitHub account does not have Copilot enabled")
        print("::error::  2. INVALID PAT TOKEN - Token expired or missing 'copilot' scope")
        print("::error::  3. NETWORK ISSUES - Unable to reach Copilot API")
        print("::error::  4. RATE LIMITING - Too many requests")
        print("::error::")
        print("::error::TO FIX: Check COPILOT_GITHUB_TOKEN in Repository Settings > Secrets")
        return EXIT_LOGIC
    if not result.output:
        print()
        print("::error::=== CLI ERROR - JOB FAILED ===")
        print(f"::error::Copilot CLI failed (exit code {result.exit_code}) with error output.")
        print(f"::error::Stderr: {result.stderr}")
        return EXIT_LOGIC
    return EXIT_OK


def write_results(config: InvokeConfig, full_prompt: str, result: AttemptResult) -> None:
    output = result.output
    if result.infrastructure_failure and not output:
        output = (
            "VERDICT: CRITICAL_FAIL\n"
            f"MESSAGE: Copilot CLI infrastructure failure (exit code {result.exit_code}). "
            "Output unavailable after retries."
        )

    config.ai_review_output_file.write_text(output + "\n", encoding="utf-8")
    append_multiline_output(config.github_output_file, "raw_output", output, "EOF_RAW")
    append_multiline_output(config.github_output_file, "stderr_output", result.stderr, "EOF_STDERR")
    append_multiline_output(
        config.github_output_file,
        "full_prompt",
        full_prompt,
        "EOF_FULL_PROMPT",
    )
    append_line(config.github_output_file, f"copilot_exit_code={result.exit_code}")
    append_line(
        config.github_output_file,
        f"infrastructure_failure={str(result.infrastructure_failure).lower()}",
    )
    append_line(config.github_output_file, f"retry_count={result.retry_count}")


def run(config: InvokeConfig) -> int:
    full_prompt = build_full_prompt(
        context_mode=config.context_mode,
        additional_context=config.additional_context,
        context_file=config.context_file,
    )
    FULL_PROMPT_PATH.write_text(full_prompt + "\n", encoding="utf-8")
    result = invoke_with_retry(config=config, full_prompt=full_prompt)
    failure_exit = analyze_non_infra_failure(result)
    if failure_exit != EXIT_OK:
        return failure_exit
    write_results(config, full_prompt, result)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print("error: no arguments are supported", file=sys.stderr)
        return EXIT_CONFIG
    try:
        config = parse_config(os.environ)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
