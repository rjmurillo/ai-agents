"""Select the session logs in a pull request that are subject to validation.

Two filters apply. The path pattern keeps only real session logs: tally files
such as ``STEP-0-METRICS.md`` live in the same directory and are not sessions.
The date cutoff keeps only logs written after the Session End checklist
requirement landed (issue #215); older logs predate the rule and cannot satisfy
it retroactively.

Writes ``has_sessions`` and ``session_files`` (a JSON array, consumed as a
matrix) to ``GITHUB_OUTPUT``.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

_SESSION_RE = re.compile(r"^\.agents/sessions/\d{4}-\d{2}-\d{2}-session-\d+.*\.(?:md|json)$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Bounded retry policy for transient rate-limit failures while enumerating
# pull request files (issue #4510). PR #4508 hit an immediate exit 3 on a
# single HTTP 403 "API rate limit exceeded" response, which failed the
# required Detect Changed Sessions check for an unrelated change. Retry only
# the rate-limit shape (HTTP 429, or HTTP 403 whose message names a rate
# limit); genuine 401 (bad credentials) and 404 (not found) are permanent and
# must fail fast.
_MAX_ATTEMPTS = 5
_BACKOFF_BASE_SECONDS = 2.0
_MAX_BACKOFF_SECONDS = 60.0

_HTTP_STATUS_PATTERN = re.compile(r"\(HTTP (\d+)\)")
_RATE_LIMIT_TEXT_PATTERN = re.compile(r"rate limit", re.IGNORECASE)
_RETRY_AFTER_PATTERN = re.compile(r"\bRetry-After:\s*(\d+)", re.IGNORECASE)
_RATE_LIMIT_RESET_PATTERN = re.compile(r"\bX-RateLimit-Reset:\s*(\d+)", re.IGNORECASE)


def _http_status(stderr: str) -> int | None:
    """Extract the HTTP status code gh reports in its error text, if any."""
    match = _HTTP_STATUS_PATTERN.search(stderr)
    return int(match.group(1)) if match else None


def _is_rate_limit_error(stderr: str) -> bool:
    """Return True when *stderr* describes a retryable rate-limit response.

    HTTP 429 is always a rate limit. HTTP 403 is ambiguous (gh reuses it for
    both permission-denied and primary/secondary rate limits), so a 403 is
    only retried when the message text names a rate limit. A permission 403
    is permanent and must fail fast, same as 401/404.
    """
    status = _http_status(stderr)
    if status == 429:
        return True
    return status == 403 and _RATE_LIMIT_TEXT_PATTERN.search(stderr) is not None


def _retry_delay_seconds(stderr: str, attempt: int) -> float:
    """Return how long to wait before the next attempt.

    Honours ``Retry-After`` first, then ``X-RateLimit-Reset`` (an epoch
    second timestamp), falling back to full-jitter exponential backoff
    (release-it.md) when neither header is present in the error text.
    """
    retry_after = _RETRY_AFTER_PATTERN.search(stderr)
    if retry_after:
        return float(retry_after.group(1))

    reset = _RATE_LIMIT_RESET_PATTERN.search(stderr)
    if reset:
        return max(float(reset.group(1)) - time.time(), 0.0)

    backoff = min(_BACKOFF_BASE_SECONDS ** (attempt - 1), _MAX_BACKOFF_SECONDS)
    return random.uniform(0, backoff)


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


class GhApiError(RuntimeError):
    """The files API could not be read."""


def changed_files(repo: str, pr_number: str) -> list[str]:
    """Return every file in the PR, from the files API.

    ``gh pr diff`` truncates on large pull requests (issue #468); the files API
    paginates instead.

    A transient rate limit (HTTP 429, or HTTP 403 naming a rate limit) is
    retried up to ``_MAX_ATTEMPTS`` times with backoff (issue #4510); a
    genuine 401 or 404 is permanent and raises on the first attempt.

    Raises ``GhApiError`` when the API call fails and is not retryable, or
    when the retry budget is exhausted. The shell original piped ``gh api``
    into ``grep ... || true``, so a failed call produced an empty list and the
    gate reported "no session files changed" -- a silent pass on an unreadable
    pull request. An unreadable pull request is unknown, not clean.
    """
    argv = [
        "gh",
        "api",
        f"repos/{repo}/pulls/{pr_number}/files",
        "--paginate",
        "--jq",
        ".[].filename",
    ]
    stderr = "gh api returned no diagnostics"
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        completed = _run(argv)
        if completed.returncode == 0:
            return [line.strip() for line in completed.stdout.splitlines() if line.strip()]

        stderr = completed.stderr.strip() or stderr
        is_last_attempt = attempt == _MAX_ATTEMPTS
        if not is_last_attempt and _is_rate_limit_error(stderr):
            delay = _retry_delay_seconds(stderr, attempt)
            print(
                f"::warning::gh api rate limited (attempt {attempt}/{_MAX_ATTEMPTS}), "
                f"retrying in {delay:.1f}s: {stderr}",
                file=sys.stderr,
            )
            time.sleep(delay)
            continue
        raise GhApiError(stderr)

    # Unreachable: the loop either returns, retries, or raises on every path.
    raise GhApiError(stderr)


def session_logs(paths: list[str]) -> list[str]:
    """Keep only paths that name a session log."""
    return [path for path in paths if _SESSION_RE.match(path)]


def partition_by_cutoff(paths: list[str], cutoff: str) -> tuple[list[str], list[str]]:
    """Split session logs into (validate, skip) around the cutoff date.

    A filename whose leading 10 characters are not a date is validated rather
    than skipped: an unparseable name is a reason to look, not to look away.
    """
    validate: list[str] = []
    skip: list[str] = []
    for path in paths:
        stamp = Path(path).name[:10]
        if _DATE_RE.match(stamp) and stamp < cutoff:
            skip.append(path)
        else:
            validate.append(path)
    return validate, skip


def _emit(has_sessions: bool, files: list[str]) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"has_sessions={'true' if has_sessions else 'false'}\n")
        handle.write(f"session_files={json.dumps(files, separators=(',', ':'))}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GH_REPO", ""))
    parser.add_argument("--pr-number", default=os.environ.get("PR_NUMBER", ""))
    parser.add_argument("--cutoff", default=os.environ.get("CUTOFF_DATE", ""))
    args = parser.parse_args(argv)

    if not args.repo or not args.pr_number or not args.cutoff:
        print("::error::repo, pr-number and cutoff are all required", file=sys.stderr)
        return 2

    try:
        found = session_logs(changed_files(args.repo, args.pr_number))
    except GhApiError as exc:
        print(f"::error::Cannot enumerate pull request files: {exc}", file=sys.stderr)
        return 3
    if not found:
        print("No session files changed")
        _emit(False, [])
        return 0

    print("All changed session files:")
    for path in found:
        print(path)

    validate, skipped = partition_by_cutoff(found, args.cutoff)

    if skipped:
        print("")
        print(f"Skipped historical sessions (before {args.cutoff}):")
        for path in skipped:
            print(path)

    if not validate:
        print("")
        print("No validatable session files (all historical)")
        _emit(False, [])
        return 0

    print("")
    print("Session files to validate:")
    for path in validate:
        print(path)
    _emit(True, validate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
