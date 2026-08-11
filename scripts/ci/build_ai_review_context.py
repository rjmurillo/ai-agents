#!/usr/bin/env python3
"""Build the ai-review composite action context outside workflow YAML."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

_outputs = cast(Any, importlib.import_module("ai_review_outputs"))
OutputConfigError = _outputs.OutputConfigError
append_multiline_output = _outputs.append_multiline_output
write_outputs = _outputs.write_outputs

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


from gh_retry_helpers import (  # isort: skip  # noqa: E402, F401
    AI_REVIEW_ACTION_DEADLINE_ENV, CommandResult, ConfigError, DIFF_TOO_LARGE,
    ExternalGhError, FILES_PER_PAGE, GH_CONTEXT_RETRY_BUDGET_SECONDS,
    GH_REFUSAL_BACKOFF_SECONDS, GH_TIMEOUT_SECONDS, GhLaunchError,
    MAX_FILE_PAGES, PERMANENT_AUTH_FAILURE, PrMetadata, ReviewContext,
    SECRET_ENVIRONMENT_VARIABLES, _GH_RETRY_DEADLINE, _failure_text,
    _new_context_retry_deadline, _redact_secrets, _retry_delay, run_gh,
)


def sanitize_title(title: str) -> str:
    cleaned = title.translate(str.maketrans("", "", '$`"\\')).strip()
    return cleaned or "Unknown PR"


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
    file_list, truncated, api_failed = get_paginated_file_list(pr_number, repository)
    return "" if api_failed or truncated else file_list


def get_paginated_file_list(pr_number: str, repository: str) -> tuple[str, bool, str]:
    files: list[str] = []
    truncated = False
    api_failure = ""
    for page in range(1, MAX_FILE_PAGES + 2):
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

        if page > MAX_FILE_PAGES:
            truncated = True
            break
        files.extend(page_files)
        if len(page_files) < FILES_PER_PAGE:
            break

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
                "Attempting --name-only transport fallback."
            )
            name_only = get_pr_name_only(pr_number, repository)
            if name_only:
                return ReviewContext(
                    f"[Large PR - showing file list only]\n{name_only}",
                    "summary",
                )
            raise ExternalGhError(
                "GitHub API pagination reached its completeness cap while fetching "
                f"PR #{pr_number}; no complete alternate file list was available"
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


def _pr_fetch_failure_context(pr_number: str, detail: str) -> ReviewContext:
    """Fail closed, naming the observed error rather than a guessed cause.

    Delegates classification to :func:`failure_classification.classify_pr_fetch_failure`;
    this wrapper handles secret redaction and ``ReviewContext`` construction.
    """
    from scripts.ci.failure_classification import classify_pr_fetch_failure

    detail = _redact_secrets(detail.strip())
    result = classify_pr_fetch_failure(pr_number, detail)
    print(result.warning)
    return ReviewContext(result.context_text, "error", True)


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

    title = _redact_secrets(metadata.title)
    body = _redact_secrets(metadata.body)
    print(f"Building context for PR #{pr_number}: {title}")
    print(f"Fetching diff for PR #{pr_number} from repository {repository}")

    try:
        built = _build_pr_diff_body(pr_number, repository, max_diff_lines)
    except ExternalGhError as exc:
        # Issue #4547: a 403 from the shared token empties the diff. Raising exits 3,
        # which skips the infra gate that writes DID_NOT_RUN, so the aggregate
        # defaults to NEEDS_REVIEW with INFRA_FAILURE false and blocks the PR.
        return _pr_fetch_failure_context(pr_number, str(exc))

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
    return ReviewContext(_redact_secrets(result.stdout.rstrip()), "full")


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
    except (ConfigError, OutputConfigError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"::error::Failed to read or write context files: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
