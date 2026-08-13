"""GitHub CLI retry and invocation helpers for ai-review scripts."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.redact_secrets import redact_ci_sink  # noqa: E402

GH_TIMEOUT_SECONDS = 60
GH_REFUSAL_BACKOFF_SECONDS = (60.0, 120.0)
# Review jobs have a 600-second deadline and model invocation may use 300
# seconds. This leaves 30 seconds before invocation and 60 seconds afterward
# for setup, classification, and artifact upload.
GH_CONTEXT_RETRY_BUDGET_SECONDS = 210.0
DOWNSTREAM_REVIEW_RESERVE_SECONDS = 360.0
AI_REVIEW_ACTION_DEADLINE_ENV = "AI_REVIEW_ACTION_DEADLINE_EPOCH"
_GH_RETRY_DEADLINE: ContextVar[float | None] = ContextVar(
    "gh_retry_deadline",
    default=None,
)
MAX_FILE_PAGES = 5
FILES_PER_PAGE = 100
DIFF_TOO_LARGE = re.compile(
    r"(HTTP 406|too_large|exceeded the maximum number of files)",
    re.IGNORECASE,
)
RETRYABLE_GH_FAILURE = re.compile(
    r"rate limit|secondary rate|abuse detection|timed out|"
    r"\bHTTP\s+(429|500|502|503|504)\b",
    re.IGNORECASE,
)
PERMANENT_AUTH_FAILURE = re.compile(
    r"\bHTTP\s+401\b|bad credentials|requires authentication|"
    r"authentication token .* could not be validated|"
    r"resource not accessible by integration|"
    r"must have admin rights|could not resolve to a pullrequest",
    re.IGNORECASE,
)
RETRY_AFTER_HEADER = re.compile(
    r"\bRetry-After:\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
RATE_LIMIT_RESET_HEADER = re.compile(
    r"\bX-RateLimit-Reset:\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
RATE_LIMIT_REMAINING_HEADER = re.compile(
    r"\bX-RateLimit-Remaining:\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
SECRET_ENVIRONMENT_VARIABLES = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "COPILOT_GITHUB_TOKEN",
    "BOT_PAT",
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True, slots=True)
class ReviewContext:
    text: str
    mode: str
    infrastructure_failure: bool = False


@dataclass(frozen=True, slots=True)
class PrMetadata:
    """Number, title, and body from one PR fetch.

    ``error`` is empty on success and otherwise carries the observed failure so
    the caller can report it instead of guessing a cause (issue #4333).
    """

    number: str
    title: str
    body: str
    error: str = ""


class ConfigError(RuntimeError):
    """Configuration prevents context output generation."""


class GhLaunchError(RuntimeError):
    """The gh process could not be launched."""


class ExternalGhError(RuntimeError):
    """GitHub or gh failed while building review context."""


def _redact_secrets(value: str | None) -> str:
    """Redact installed values, wrappers, and recognized credential shapes."""
    secret_values = (os.environ.get(variable, "") for variable in SECRET_ENVIRONMENT_VARIABLES)
    return redact_ci_sink(value or "", secret_values=secret_values).text


def _failure_text(result: CommandResult) -> str:
    return f"{result.stderr}\n{result.stdout}".strip()


def _retry_delay(refusal: str, fallback: float) -> tuple[float, str]:
    retry_after = RETRY_AFTER_HEADER.search(refusal)
    if retry_after:
        return max(0.0, float(retry_after.group(1))), "Retry-After"

    reset = RATE_LIMIT_RESET_HEADER.search(refusal)
    remaining = RATE_LIMIT_REMAINING_HEADER.search(refusal)
    if reset and (remaining is None or float(remaining.group(1)) == 0):
        wait = max(0.0, float(reset.group(1)) - time.time() + 1.0)
        return wait, "X-RateLimit-Reset"

    return fallback, "exponential backoff"


def _with_retry_exhausted(result: CommandResult, reason: str) -> CommandResult:
    detail = _failure_text(result)
    diagnostic = f"{detail}\n{reason}".strip()
    return CommandResult(result.stdout, diagnostic, result.returncode)


def _new_context_retry_deadline() -> float:
    """Cap context retries against the deadline established before action setup."""
    now = time.monotonic()
    budget = GH_CONTEXT_RETRY_BUDGET_SECONDS
    raw_action_deadline = os.environ.get(AI_REVIEW_ACTION_DEADLINE_ENV, "")
    if raw_action_deadline:
        try:
            remaining = float(raw_action_deadline) - time.time() - DOWNSTREAM_REVIEW_RESERVE_SECONDS
        except ValueError:
            remaining = 0.0
        budget = min(budget, remaining)
    return now + max(0.0, budget)


def _invoke_gh_once(arguments: list[str], timeout: float) -> CommandResult:
    command_arguments = arguments
    if arguments[:2] == ["pr", "diff"] and "--repo" in arguments:
        repository_index = arguments.index("--repo") + 1
        if repository_index < len(arguments) and "--name-only" not in arguments:
            command_arguments = [
                "api",
                f"repos/{arguments[repository_index]}/pulls/{arguments[2]}",
                "--method",
                "GET",
                "--header",
                "Accept: application/vnd.github.v3.diff",
            ]
    include_response_headers = command_arguments[:1] == ["api"] and not any(
        argument in {"--include", "-i"} for argument in command_arguments
    )
    command_arguments = [
        *command_arguments,
        *(["--include"] if include_response_headers else []),
    ]
    try:
        completed = subprocess.run(
            ["gh", *command_arguments],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(
            _redact_secrets(stdout),
            _redact_secrets(f"{stderr}\ngh command timed out after {exc.timeout} seconds").strip(),
            124,
        )
    except OSError as exc:
        raise GhLaunchError(f"Failed to run gh: {exc}") from exc

    # Successful stdout may be serialized JSON. Keep it parseable in memory;
    # write_outputs and the invocation sink redact extracted context later.
    # Failed stdout can enter diagnostics, so redact it before returning.
    stdout = completed.stdout
    response_headers = ""
    if include_response_headers:
        header_block, separator, response_body = stdout.partition("\n\n")
        if separator and re.match(r"HTTP/\S+\s+\d{3}\b", header_block):
            response_headers = header_block
            stdout = response_body
    if completed.returncode != 0:
        stdout = _redact_secrets(stdout)
    stderr = completed.stderr
    if completed.returncode != 0 and response_headers:
        stderr = f"{response_headers}\n{stderr}".strip()
    return CommandResult(
        stdout,
        _redact_secrets(stderr),
        completed.returncode,
    )


def run_gh(arguments: list[str], timeout: int = GH_TIMEOUT_SECONDS) -> CommandResult:
    attempts = len(GH_REFUSAL_BACKOFF_SECONDS) + 1
    for attempt in range(attempts):
        deadline = _GH_RETRY_DEADLINE.get()
        remaining = deadline - time.monotonic() if deadline is not None else None
        if remaining is not None and remaining <= 0:
            return CommandResult("", "GitHub API retry budget exhausted", 124)

        command_timeout = min(timeout, remaining) if remaining is not None else timeout
        result = _invoke_gh_once(arguments, command_timeout)

        if result.returncode == 0:
            return result

        refusal = _failure_text(result)
        if PERMANENT_AUTH_FAILURE.search(refusal):
            return result
        if not RETRYABLE_GH_FAILURE.search(refusal):
            return result
        if attempt >= len(GH_REFUSAL_BACKOFF_SECONDS):
            return _with_retry_exhausted(
                result,
                f"GitHub API retry attempts exhausted after {attempts} attempts",
            )

        delay, source = _retry_delay(
            refusal,
            GH_REFUSAL_BACKOFF_SECONDS[attempt],
        )
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if delay + 1.0 >= remaining:
                return _with_retry_exhausted(
                    result,
                    "GitHub API retry budget exhausted before the next allowed attempt",
                )
        print(f"::warning::GitHub API transient refusal. Retrying in {delay:.0f}s using {source}.")
        time.sleep(delay)

    raise RuntimeError("unreachable gh retry loop")

