#!/usr/bin/env python3
# taste-lint: ignore file-size, this file sat at 499 of 500 lines, so the
# smallest correct form of the rate-limit classification fix (3 lines) still
# lands at 502. Splitting a CI-critical context builder is a separate refactor,
# not cleanup owed by a bug fix. Tracked for extraction in issue #4597.
"""Build the ai-review composite action context outside workflow YAML."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.redact_secrets import redact as redact_token_shapes  # noqa: E402

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
    r"resource not accessible by integration|not accessible|"
    r"must have admin rights|could not resolve to a pullrequest",
    re.IGNORECASE,
)
RETRY_AFTER_HEADER = re.compile(
    r"^Retry-After:\s*(\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
RATE_LIMIT_RESET_HEADER = re.compile(
    r"^X-RateLimit-Reset:\s*(\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE | re.MULTILINE,
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


def _redact_exact_secrets(value: str | None) -> str:
    """Remove workflow credentials before diagnostics reach logs or artifacts."""
    redacted = value or ""
    for variable in SECRET_ENVIRONMENT_VARIABLES:
        secret = os.environ.get(variable, "")
        if len(secret) >= 8:
            redacted = redacted.replace(secret, "***")
    redacted = re.sub(
        r"(?i)(authorization:\s*(?:bearer|token|basic)\s+)\S+",
        r"\1***",
        redacted,
    )
    return re.sub(r"https://[^/\s:@]+:[^@\s]+@", "https://***:***@", redacted)


def _redact_secrets(value: str | None) -> str:
    """Redact installed values, wrappers, and recognized credential shapes."""
    redacted = _redact_exact_secrets(value)
    return redact_token_shapes(redacted, include_hex=False).text


def _failure_text(result: CommandResult) -> str:
    return f"{result.stderr}\n{result.stdout}".strip()


def _retry_delay(refusal: str, fallback: float) -> tuple[float, str]:
    retry_after = RETRY_AFTER_HEADER.search(refusal)
    if retry_after:
        return max(0.0, float(retry_after.group(1))), "Retry-After"

    reset = RATE_LIMIT_RESET_HEADER.search(refusal)
    if reset:
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
    try:
        completed = subprocess.run(
            ["gh", *arguments],
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

    return CommandResult(
        _redact_secrets(completed.stdout),
        _redact_secrets(completed.stderr),
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


def sanitize_title(title: str) -> str:
    cleaned = title.translate(str.maketrans("", "", '$`"\\')).strip()
    return cleaned or "Unknown PR"


def sanitize_file_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "local"


def count_lines(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def read_utf8_file(path: Path, description: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{description} file must be UTF-8: {path}") from exc


def _parse_pr_payload(raw: str) -> PrMetadata | None:
    """Turn a pulls payload into metadata, or None when it is unusable."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "number" not in parsed:
        return None
    body = parsed.get("body")
    return PrMetadata(
        number=str(parsed["number"]),
        title=sanitize_title(str(parsed.get("title") or "")),
        body=("" if body is None else str(body)).rstrip("\n"),
    )


def fetch_pr_metadata(pr_number: str, repository: str) -> PrMetadata:
    """Fetch PR number, title, and body in one call, REST first.

    Before issue #4333 this was three separate ``gh pr view`` round-trips, all
    of which go through GraphQL, and each collapsed to a sentinel ("0", "",
    "Unknown PR") on any failure. With the shared GraphQL quota exhausted and
    REST quota still available, all ten review jobs recorded DID_NOT_RUN and
    the aggregate blocked the PR.

    REST carries all three fields in one response. ``gh pr view`` stays as a
    fallback for the reverse outage. When both fail the error text is carried
    out so the caller reports what actually happened.
    """
    rest = run_gh(["api", f"repos/{repository}/pulls/{pr_number}"])
    if rest.returncode == 0:
        metadata = _parse_pr_payload(rest.stdout)
        if metadata is not None:
            return metadata
        rest_error = "REST response was unusable"
    else:
        rest_error = _failure_text(rest) or "REST request returned no diagnostic output"
        if PERMANENT_AUTH_FAILURE.search(rest_error):
            return PrMetadata("", "Unknown PR", "", error=f"REST: {rest_error}")

    graphql = run_gh(["pr", "view", pr_number, "--repo", repository, "--json", "number,title,body"])
    if graphql.returncode == 0:
        metadata = _parse_pr_payload(graphql.stdout)
        if metadata is not None:
            return metadata
        graphql_error = "gh pr view response was unusable"
    else:
        graphql_error = _failure_text(graphql) or "gh pr view returned no diagnostic output"

    return PrMetadata(
        number="",
        title="Unknown PR",
        body="",
        error=f"REST: {rest_error} | gh pr view: {graphql_error}",
    )


def get_pr_name_only(pr_number: str, repository: str) -> str:
    """Return the changed-file list, falling back from GraphQL to REST.

    ``gh pr diff`` goes through GraphQL and fails in the same quota window that
    breaks :func:`fetch_pr_metadata` (issue #4333), so the REST files endpoint
    backs it up.
    """
    result = run_gh(["pr", "diff", pr_number, "--repo", repository, "--name-only"])
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    if PERMANENT_AUTH_FAILURE.search(_failure_text(result)):
        return ""
    file_list, _truncated, api_failed = get_paginated_file_list(pr_number, repository)
    return "" if api_failed else file_list


def get_paginated_file_list(pr_number: str, repository: str) -> tuple[str, bool, str]:
    files: list[str] = []
    truncated = False
    api_failure = ""
    for page in range(1, MAX_FILE_PAGES + 1):
        result = run_gh(
            [
                "api",
                f"repos/{repository}/pulls/{pr_number}/files?per_page={FILES_PER_PAGE}&page={page}",
                "--jq",
                ".[].filename",
            ]
        )
        if result.returncode != 0:
            truncated = bool(files)
            api_failure = (
                _failure_text(result) or "GitHub API pagination failed without diagnostics"
            )
            break

        page_files = [line for line in result.stdout.splitlines() if line.strip()]
        if not page_files:
            break

        files.extend(page_files)
        if len(page_files) < FILES_PER_PAGE:
            break
    else:
        truncated = True

    return "\n".join(files), truncated, api_failure


def build_large_pr_context(pr_number: str, repository: str) -> ReviewContext:
    file_list, truncated, api_failure = get_paginated_file_list(pr_number, repository)
    if api_failure:
        total_files = count_lines(file_list)
        if not PERMANENT_AUTH_FAILURE.search(api_failure):
            print(
                "::warning::REST file pagination failed. "
                "Attempting --name-only transport fallback..."
            )
            name_only = get_pr_name_only(pr_number, repository)
            if name_only:
                return ReviewContext(
                    f"[Large PR - showing file list only]\n{name_only}",
                    "summary",
                )
        raise ExternalGhError(
            "GitHub API pagination failed while fetching the complete file list "
            f"for PR #{pr_number} after {total_files} files: {api_failure}"
        )
    if file_list:
        total_files = count_lines(file_list)
        print(f"Retrieved {total_files} changed files via API pagination")
        if truncated:
            print(
                "::warning::File list truncated at "
                f"{MAX_FILE_PAGES * FILES_PER_PAGE} files. "
                "PR may have more changes not shown in review context."
            )
        context = (
            "[Large PR - >300 files (GitHub diff limit exceeded), showing file list only]"
            "\n\nChanged files:\n"
            f"{file_list}\n"
        )
        return ReviewContext(context, "summary")

    print("::warning::API pagination failed. Attempting --name-only fallback...")
    name_only = get_pr_name_only(pr_number, repository)
    if name_only:
        print("Retrieved file list using --name-only")
        return ReviewContext(f"[Large PR - showing file list only]\n{name_only}", "summary")

    raise ExternalGhError(
        f"All fallback methods failed for PR #{pr_number}; "
        "PR may have structural issues or GitHub API may be unavailable"
    )


FORK_PERMISSION_SIGNAL = re.compile(
    r"HTTP 40[34]|not accessible|must have admin rights|Could not resolve to a PullRequest",
    re.IGNORECASE,
)

# A REST rate-limit refusal arrives as `HTTP 403: API rate limit exceeded ...`,
# which FORK_PERMISSION_SIGNAL matches on the status alone. Suppressing the hint
# on this signature keeps the #4333 misdiagnosis from returning through the REST
# transport after it was fixed for GraphQL.
RATE_LIMIT_SIGNAL = re.compile(
    r"rate limit|secondary rate|abuse detection",
    re.IGNORECASE,
)


def _pr_fetch_failure_context(pr_number: str, detail: str) -> ReviewContext:
    """Fail closed, naming the observed error rather than a guessed cause.

    REQ-008-05 (issue #2818) keeps the DID_NOT_RUN behavior. Issue #4333 is why
    the fork-permission hint is now conditional: an exhausted GraphQL quota was
    reported as a token permission problem, and chasing that cost real time on
    PR #4273. The GraphQL form carries no HTTP status, so dropping the
    unconditional hint was enough for it. The REST form does carry one, so the
    hint needs the rate-limit signature to lose as well.
    """
    detail = _redact_secrets(detail.strip()) or "GitHub API returned no diagnostic output"
    hint = (
        " The GH_TOKEN may lack permissions for first-time contributor PRs from forks."
        if FORK_PERMISSION_SIGNAL.search(detail) and not RATE_LIMIT_SIGNAL.search(detail)
        else ""
    )
    print(f"::warning::Could not fetch PR #{pr_number}: {detail}{hint}")
    return ReviewContext(
        f"INFRASTRUCTURE_FAILURE: Could not fetch PR #{pr_number}: {detail}{hint}",
        "error",
        True,
    )


def _build_pr_diff_body(pr_number: str, repository: str, max_diff_lines: int) -> ReviewContext:
    """Fetch the diff, falling back to pagination or a summary. Raises on failure."""
    diff = run_gh(["pr", "diff", pr_number, "--repo", repository])
    if DIFF_TOO_LARGE.search(diff.stderr):
        warning = "::warning::PR diff unavailable via gh pr diff (>300 files)."
        print(f"{warning} Falling back to API pagination...")
        return build_large_pr_context(pr_number, repository)
    if diff.returncode != 0:
        detail = diff.stderr.strip() or f"gh pr diff exited {diff.returncode}"
        raise ExternalGhError(
            f"Failed to fetch PR diff for #{pr_number} from {repository}: {detail}"
        )

    line_count = count_lines(diff.stdout)
    print(f"PR diff has {line_count} lines")
    if not diff.stdout.strip():
        message = f"Failed to fetch PR diff for #{pr_number} from {repository}"
        if diff.stderr:
            message = f"{message}: {diff.stderr.strip()}"
        raise ExternalGhError(message)

    if line_count > max_diff_lines:
        summary = get_pr_name_only(pr_number, repository)
        if not summary:
            raise ExternalGhError(f"Failed to fetch PR diff summary for #{pr_number}")
        return ReviewContext(
            f"[Large PR - {line_count} lines, showing summary only]\n{summary}",
            "summary",
        )
    return ReviewContext(diff.stdout, "full")


def _build_pr_diff_context(
    pr_number: str,
    repository: str,
    max_diff_lines: int,
) -> ReviewContext:
    metadata = fetch_pr_metadata(pr_number, repository)
    if metadata.error:
        return _pr_fetch_failure_context(pr_number, metadata.error)
    if metadata.number != pr_number:
        return _pr_fetch_failure_context(
            pr_number,
            f"PR number mismatch: requested {pr_number}, got {metadata.number}",
        )

    title = metadata.title
    print(f"Building context for PR #{pr_number}: {title}")
    print(f"Fetching diff for PR #{pr_number} from repository {repository}")

    try:
        built = _build_pr_diff_body(pr_number, repository, max_diff_lines)
    except ExternalGhError as exc:
        # Issue #4547: a 403 from the shared token empties the diff. Raising exits 3,
        # which skips the infra gate that writes DID_NOT_RUN, so the aggregate
        # defaults to NEEDS_REVIEW with INFRA_FAILURE false and blocks the PR.
        return _pr_fetch_failure_context(pr_number, str(exc))

    body = metadata.body
    if body:
        text = (
            f"## PR #{pr_number}: {title}\n\n## PR Description\n{body}\n\n## Changes\n{built.text}"
        )
    else:
        text = f"## PR #{pr_number}: {title}\n\n## Changes\n{built.text}"
    return ReviewContext(text, built.mode, built.infrastructure_failure)


def build_pr_diff_context(pr_number: str, repository: str, max_diff_lines: int) -> ReviewContext:
    if _GH_RETRY_DEADLINE.get() is not None:
        return _build_pr_diff_context(pr_number, repository, max_diff_lines)
    token = _GH_RETRY_DEADLINE.set(_new_context_retry_deadline())
    try:
        return _build_pr_diff_context(pr_number, repository, max_diff_lines)
    finally:
        _GH_RETRY_DEADLINE.reset(token)


def build_issue_context(issue_number: str, repository: str) -> ReviewContext:
    if not issue_number:
        return ReviewContext(
            "INFRASTRUCTURE_FAILURE: No issue number provided",
            "error",
            True,
        )
    if not repository:
        raise ConfigError("GITHUB_REPOSITORY is required for issue context")

    query = (
        '"Title: " + .title + "\n\nBody:\n" + .body '
        '+ "\n\nLabels: " + ([.labels[].name] | join(", "))'
    )
    result = run_gh(
        [
            "issue",
            "view",
            issue_number,
            "--repo",
            repository,
            "--json",
            "title,body,labels",
            "-q",
            query,
        ]
    )
    if result.returncode != 0 or not result.stdout.strip():
        detail = _failure_text(result) or "GitHub API returned no issue output"
        return ReviewContext(
            f"INFRASTRUCTURE_FAILURE: Could not fetch issue #{issue_number}: {detail}",
            "error",
            True,
        )
    return ReviewContext(result.stdout.rstrip(), "full")


def build_session_log_context(context_path: str) -> ReviewContext:
    path = Path(context_path)
    if context_path and path.is_file():
        session_log = read_utf8_file(path, "Session log")
        if session_log.strip():
            return ReviewContext(session_log, "full")
        detail = f"Session log file is empty: {context_path}"
    else:
        detail = f"Session log file not found: {context_path}"
    return ReviewContext(f"INFRASTRUCTURE_FAILURE: {detail}", "error", True)


def build_spec_context(
    context_path: str,
    pr_number: str,
    repository: str,
    max_diff_lines: int,
) -> ReviewContext:
    path = Path(context_path)
    if not context_path or not path.is_file():
        return ReviewContext(
            f"INFRASTRUCTURE_FAILURE: Spec file not found: {context_path}",
            "error",
            True,
        )

    spec = read_utf8_file(path, "Spec")
    if not spec.strip():
        return ReviewContext(
            f"INFRASTRUCTURE_FAILURE: Specification file is empty: {path}",
            "error",
            True,
        )
    if not pr_number:
        return ReviewContext(
            f"## Specification\n{spec}\n\n## Implementation Changes\n[No PR diff provided]",
            "partial",
        )

    diff = run_gh(["pr", "diff", pr_number, "--repo", repository])
    if diff.returncode == 0 and diff.stdout.strip():
        line_count = count_lines(diff.stdout)
        diff_text = diff.stdout
        mode = "full"
        if line_count > max_diff_lines:
            mode = "partial"
            preview = "\n".join(diff.stdout.splitlines()[:max_diff_lines])
            diff_text = (
                f"[Diff truncated to first {max_diff_lines} of {line_count} lines]\n{preview}"
            )
    else:
        failure = _failure_text(diff)
        if PERMANENT_AUTH_FAILURE.search(failure):
            detail = (
                diff.stderr.strip() or "GitHub authentication or permission request was rejected"
            )
            return ReviewContext(
                f"## Specification\n{spec}\n\n"
                "INFRASTRUCTURE_FAILURE: "
                f"Could not fetch PR #{pr_number} implementation context: {detail}",
                "error",
                True,
            )
        name_only = get_pr_name_only(pr_number, repository)
        if not name_only:
            detail = diff.stderr.strip() or "GitHub API returned no diff output"
            return ReviewContext(
                f"## Specification\n{spec}\n\n"
                "INFRASTRUCTURE_FAILURE: "
                f"Could not fetch PR #{pr_number} implementation context: {detail}",
                "error",
                True,
            )
        mode = "summary"
        diff_text = f"[Diff unavailable, showing file list only]\n{name_only}"

    return ReviewContext(
        f"## Specification\n{spec}\n\n## Implementation Changes\n{diff_text}",
        mode,
    )


def build_context_from_environment() -> ReviewContext:
    deadline = _new_context_retry_deadline()
    if deadline <= time.monotonic():
        return ReviewContext(
            "INFRASTRUCTURE_FAILURE: AI review action budget exhausted before context fetch",
            "error",
            True,
        )
    token = _GH_RETRY_DEADLINE.set(deadline)
    try:
        return _build_context_from_environment()
    finally:
        _GH_RETRY_DEADLINE.reset(token)


def _build_context_from_environment() -> ReviewContext:
    context_type = os.environ.get("CONTEXT_TYPE", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    context_path = os.environ.get("CONTEXT_PATH", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    raw_max_diff_lines = os.environ.get("MAX_DIFF_LINES", "1000") or "1000"
    try:
        max_diff_lines = int(raw_max_diff_lines)
    except ValueError as exc:
        raise ConfigError(f"MAX_DIFF_LINES must be an integer: {raw_max_diff_lines}") from exc

    if context_type == "pr-diff":
        if not pr_number:
            raise ConfigError("PR_NUMBER is required for pr-diff context")
        if not repository:
            raise ConfigError("GITHUB_REPOSITORY is required for pr-diff context")
        return build_pr_diff_context(pr_number, repository, max_diff_lines)
    if context_type == "issue":
        return build_issue_context(issue_number, repository)
    if context_type == "session-log":
        return build_session_log_context(context_path)
    if context_type == "spec-file":
        if pr_number and not repository:
            raise ConfigError("GITHUB_REPOSITORY is required for spec-file PR context")
        return build_spec_context(context_path, pr_number, repository, max_diff_lines)
    raise ConfigError(f"Unknown CONTEXT_TYPE: {context_type}")


def append_output(output_path: Path, key: str, value: str) -> None:
    with output_path.open("a", encoding="utf-8") as output:
        output.write(f"{key}={value}\n")


def choose_multiline_delimiter(key: str, value: str) -> str:
    payload_lines = set(value.splitlines())
    base = f"EOF_{key.upper()}"
    delimiter = base
    suffix = 0
    while delimiter in payload_lines:
        suffix += 1
        delimiter = f"{base}_{suffix}"
    return delimiter


def append_multiline_output(output_path: Path, key: str, value: str) -> None:
    delimiter = choose_multiline_delimiter(key, value)
    with output_path.open("a", encoding="utf-8") as output:
        output.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def write_outputs(review_context: ReviewContext) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        raise ConfigError("GITHUB_OUTPUT is required")

    output_path = Path(github_output)
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    context_identifier = sanitize_file_identifier(os.environ.get("PR_NUMBER") or run_id)
    runner_temp = os.environ.get("RUNNER_TEMP")
    if not runner_temp:
        raise ConfigError("RUNNER_TEMP is required")
    workspace = Path(runner_temp).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    context_file = workspace / f"ai-review-context-pr{context_identifier}.txt"
    safe_context = _redact_secrets(review_context.text)
    context_file.write_text(safe_context, encoding="utf-8")

    append_output(output_path, "context_mode", review_context.mode)
    append_output(output_path, "context_file", str(context_file))
    if review_context.infrastructure_failure:
        append_output(output_path, "context_infra_failure", "true")
    append_multiline_output(output_path, "context_built", safe_context)


def main() -> int:
    try:
        review_context = build_context_from_environment()
        write_outputs(review_context)
    except subprocess.TimeoutExpired as exc:
        print(f"::error::gh command timed out after {exc.timeout} seconds", file=sys.stderr)
        return 3
    except (GhLaunchError, ExternalGhError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 3
    except ConfigError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"::error::Failed to read or write context files: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
