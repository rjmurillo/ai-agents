#!/usr/bin/env python3
"""Build the ai-review composite action context outside workflow YAML."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

GH_TIMEOUT_SECONDS = 60
MAX_FILE_PAGES = 5
FILES_PER_PAGE = 100
DIFF_TOO_LARGE = re.compile(
    r"(HTTP 406|too_large|exceeded the maximum number of files)",
    re.IGNORECASE,
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


def run_gh(arguments: list[str], timeout: int = GH_TIMEOUT_SECONDS) -> CommandResult:
    result = subprocess.run(
        ["gh", *arguments],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return CommandResult(result.stdout, result.stderr, result.returncode)


def sanitize_title(title: str) -> str:
    cleaned = title.translate(str.maketrans("", "", '$`"\\')).strip()
    return cleaned or "Unknown PR"


def count_lines(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def get_pr_title(pr_number: str, repository: str) -> str:
    result = run_gh(
        ["pr", "view", pr_number, "--repo", repository, "--json", "title", "-q", ".title"]
    )
    if result.returncode != 0:
        return "Unknown PR"
    return sanitize_title(result.stdout)


def get_pr_body(pr_number: str, repository: str) -> str:
    result = run_gh(
        ["pr", "view", pr_number, "--repo", repository, "--json", "body", "-q", ".body"]
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def get_actual_pr_number(pr_number: str, repository: str) -> str:
    result = run_gh(
        ["pr", "view", pr_number, "--repo", repository, "--json", "number", "-q", ".number"]
    )
    if result.returncode != 0:
        return "0"
    return result.stdout.strip() or "0"


def get_pr_name_only(pr_number: str, repository: str) -> str:
    result = run_gh(["pr", "diff", pr_number, "--repo", repository, "--name-only"])
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def get_paginated_file_list(pr_number: str, repository: str) -> tuple[str, bool]:
    files: list[str] = []
    truncated = False
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
            break

        page_files = [line for line in result.stdout.splitlines() if line.strip()]
        if not page_files:
            break

        files.extend(page_files)
        if len(page_files) < FILES_PER_PAGE:
            break
    else:
        truncated = True

    return "\n".join(files), truncated


def build_large_pr_context(pr_number: str, repository: str) -> ReviewContext:
    file_list, truncated = get_paginated_file_list(pr_number, repository)
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

    print(f"::error::All fallback methods failed for PR #{pr_number}")
    print("::error::PR may have structural issues or GitHub API may be unavailable")
    raise SystemExit(1)


def build_pr_diff_context(pr_number: str, repository: str, max_diff_lines: int) -> ReviewContext:
    title = get_pr_title(pr_number, repository)
    print(f"Building context for PR #{pr_number}: {title}")
    print(f"Fetching diff for PR #{pr_number} from repository {repository}")

    actual_pr = get_actual_pr_number(pr_number, repository)
    if actual_pr != pr_number:
        print(
            "::warning::PR number mismatch: "
            f"requested {pr_number}, got {actual_pr}. "
            "Token may lack permissions for first-time contributor PRs from forks."
        )
        return ReviewContext(
            "INFRASTRUCTURE_FAILURE: "
            f"Could not fetch PR #{pr_number}. "
            "The GH_TOKEN may lack permissions for first-time contributor PRs from forks.",
            "error",
            True,
        )

    diff = run_gh(["pr", "diff", pr_number, "--repo", repository])
    if DIFF_TOO_LARGE.search(diff.stderr):
        print(
            "::warning::PR diff unavailable via gh pr diff (>300 files). "
            "Falling back to API pagination..."
        )
        built = build_large_pr_context(pr_number, repository)
    else:
        line_count = count_lines(diff.stdout)
        print(f"PR diff has {line_count} lines")
        if line_count == 0:
            print(f"::error::Failed to fetch PR diff for #{pr_number} from {repository}")
            if diff.stderr:
                print(f"::error::Error details: {diff.stderr.strip()}")
            raise SystemExit(1)

        if line_count > max_diff_lines:
            summary = get_pr_name_only(pr_number, repository)
            if not summary:
                print(f"::error::Failed to fetch PR diff summary for #{pr_number}")
                raise SystemExit(1)
            built = ReviewContext(
                f"[Large PR - {line_count} lines, showing summary only]\n{summary}",
                "summary",
            )
        else:
            built = ReviewContext(diff.stdout, "full")

    body = get_pr_body(pr_number, repository)
    if body:
        text = (
            f"## PR #{pr_number}: {title}\n\n"
            f"## PR Description\n{body}\n\n"
            f"## Changes\n{built.text}"
        )
    else:
        text = f"## PR #{pr_number}: {title}\n\n## Changes\n{built.text}"
    return ReviewContext(text, built.mode, built.infrastructure_failure)


def build_issue_context(issue_number: str) -> ReviewContext:
    if not issue_number:
        return ReviewContext("No issue number provided", "full")

    query = (
        '"Title: " + .title + "\n\nBody:\n" + .body '
        '+ "\n\nLabels: " + ([.labels[].name] | join(", "))'
    )
    result = run_gh(
        ["issue", "view", issue_number, "--json", "title,body,labels", "-q", query]
    )
    if result.returncode != 0:
        return ReviewContext("Unable to get issue", "full")
    return ReviewContext(result.stdout.rstrip(), "full")


def build_session_log_context(context_path: str) -> ReviewContext:
    path = Path(context_path)
    if context_path and path.is_file():
        return ReviewContext(path.read_text(encoding="utf-8"), "full")
    return ReviewContext(f"Session log file not found: {context_path}", "full")


def build_spec_context(
    context_path: str,
    pr_number: str,
    repository: str,
    max_diff_lines: int,
) -> ReviewContext:
    path = Path(context_path)
    if not context_path or not path.is_file():
        return ReviewContext(f"Spec file not found: {context_path}", "full")

    spec = path.read_text(encoding="utf-8")
    if not pr_number:
        return ReviewContext(
            f"## Specification\n{spec}\n\n## Implementation Changes\n[No PR diff provided]",
            "partial",
        )

    diff = run_gh(["pr", "diff", pr_number, "--repo", repository])
    if diff.returncode == 0 and diff.stdout:
        line_count = count_lines(diff.stdout)
        diff_text = diff.stdout
        mode = "full"
        if line_count > max_diff_lines:
            mode = "partial"
            preview = "\n".join(diff.stdout.splitlines()[:max_diff_lines])
            diff_text = (
                f"[Diff truncated to first {max_diff_lines} of "
                f"{line_count} lines]\n{preview}"
            )
    else:
        mode = "summary"
        name_only = get_pr_name_only(pr_number, repository)
        diff_text = (
            f"[Diff unavailable, showing file list only]\n{name_only}"
            if name_only
            else "[Diff unavailable]"
        )

    return ReviewContext(
        f"## Specification\n{spec}\n\n## Implementation Changes\n{diff_text}",
        mode,
    )


def build_context_from_environment() -> ReviewContext:
    context_type = os.environ.get("CONTEXT_TYPE", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    context_path = os.environ.get("CONTEXT_PATH", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    max_diff_lines = int(os.environ.get("MAX_DIFF_LINES", "1000") or "1000")

    if context_type == "pr-diff":
        if not pr_number:
            return ReviewContext("No PR number provided", "full")
        return build_pr_diff_context(pr_number, repository, max_diff_lines)
    if context_type == "issue":
        return build_issue_context(issue_number)
    if context_type == "session-log":
        return build_session_log_context(context_path)
    if context_type == "spec-file":
        return build_spec_context(context_path, pr_number, repository, max_diff_lines)
    return ReviewContext(f"Unknown context type: {context_type}", "full")


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
        raise SystemExit("GITHUB_OUTPUT is required")

    output_path = Path(github_output)
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    pr_number = os.environ.get("PR_NUMBER") or run_id
    workspace = Path(os.environ.get("RUNNER_TEMP", ".")).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    context_file = workspace / f"ai-review-context-pr{pr_number}.txt"
    context_file.write_text(review_context.text, encoding="utf-8")

    append_output(output_path, "context_mode", review_context.mode)
    append_output(output_path, "context_file", str(context_file))
    if review_context.infrastructure_failure:
        append_output(output_path, "context_infra_failure", "true")
    append_multiline_output(output_path, "context_built", review_context.text)


def main() -> int:
    try:
        review_context = build_context_from_environment()
        write_outputs(review_context)
    except subprocess.TimeoutExpired as exc:
        print(f"::error::gh command timed out after {exc.timeout} seconds", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"::error::Failed to run gh: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
