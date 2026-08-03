#!/usr/bin/env python3
"""Request a PR review from the bot over REST, with bounded retry.

The workflow previously ran a bare ``gh pr edit --add-reviewer``. That path
goes through GraphQL, and it failed on PRs #4325, #4328, #4330, and #4331 in one
window with "GraphQL: API rate limit already exceeded for user ID 6811113",
leaving the reviewer unassigned and the job red (issue #4335). REST kept serving
throughout that window.

``POST /repos/{owner}/{repo}/pulls/{number}/requested_reviewers`` needs exactly
the ``pull-requests: write`` scope the workflow already declares.

The token stays ``secrets.BOT_PAT`` on purpose. Requesting the review with the
job's own ``GITHUB_TOKEN`` would drop the shared-quota coupling the issue names,
but GitHub does not dispatch new workflow runs from events an Actions token
raised, and ``.github/workflows/rjmurillo-bot.yml`` triggers on
``pull_request_target: types: [review_requested]``. The swap would silence the
bot review it exists to start.

Exit codes (ADR-035):
    0 - Reviewer requested, or already requested.
    2 - Configuration error (missing or malformed arguments).
    3 - External error after the retry budget is spent.
    4 - Authentication error.

``--tolerate-external`` downgrades exit 3 to exit 0 after printing a
``::warning::``. It exists so a lost race against a rate limit does not red a
job that is not one of the required checks. It is deliberately narrower than
``continue-on-error: true`` on the step: a blanket tolerance also swallows exit
4, so an expired or revoked ``secrets.BOT_PAT`` would read as a green job
forever with a missing bot review as the only symptom. Auth and config failures
still fail the step.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.github_core.api import (  # noqa: E402
    REFUSAL_BACKOFF_SECONDS,
    GhAuthStatus,
    classify_gh_failure_text,
)

# One attempt per rung, plus the first. The ladder is the shared one, sized to
# the recovery measured on issue #4326 ("the next call of the same shape
# succeeded about a minute later"). The 5s-then-10s budget this started with
# spent 15s against that condition, which is inside the same window.
MAX_ATTEMPTS = len(REFUSAL_BACKOFF_SECONDS) + 1
GH_TIMEOUT_SECONDS = 30

_EXIT_OK = 0
_EXIT_CONFIG = 2
_EXIT_EXTERNAL = 3
_EXIT_AUTH = 4

# A refusal that clears on its own. These are the shapes measured on issue
# #4326: quota and secondary limits arrive as HTTP 403 with rate-limit wording,
# and 5xx is an upstream wobble.
_RETRYABLE = frozenset(
    {
        GhAuthStatus.RATE_LIMITED,
        GhAuthStatus.SECONDARY_RATE_LIMITED,
        GhAuthStatus.TRANSIENT_ERROR,
    }
)

# classify_gh_failure_text falls through to INVALID_CREDENTIALS, which is right
# for its own caller (an unexplained `gh auth status` failure is an auth
# failure) and wrong here: a 404 or 422 from the REST endpoint is neither auth
# nor retryable. Exit 4 needs the message to actually name an auth condition.
_AUTH_SIGNAL = re.compile(r"HTTP 401|bad credentials|requires authentication", re.IGNORECASE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--pull-request", required=True, help="PR number")
    parser.add_argument("--reviewer", required=True, help="Login to request")
    parser.add_argument(
        "--tolerate-external",
        action="store_true",
        help=(
            "Exit 0 after warning when the retry budget is spent. Auth and "
            "config failures still exit non-zero."
        ),
    )
    return parser


def _request_review(repo: str, pr_number: str, reviewer: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{repo}/pulls/{pr_number}/requested_reviewers",
            "-f",
            f"reviewers[]={reviewer}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GH_TIMEOUT_SECONDS,
    )


def assign_reviewer(
    repo: str,
    pr_number: str,
    reviewer: str,
    sleep: Callable[[float], object] | None = None,
) -> int:
    """Request the review, retrying refusals that clear on their own.

    ``sleep`` is resolved at call time, not bound as a default, so a test that
    patches ``time.sleep`` actually intercepts it.
    """
    wait = time.sleep if sleep is None else sleep
    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = _request_review(repo, pr_number, reviewer)
        except FileNotFoundError:
            print("gh CLI not found on PATH", file=sys.stderr)
            return _EXIT_CONFIG
        except subprocess.TimeoutExpired:
            last_error = f"gh timed out after {GH_TIMEOUT_SECONDS}s"
            status = GhAuthStatus.TRANSIENT_ERROR
        else:
            if result.returncode == 0:
                print(f"Requested review from {reviewer} on PR #{pr_number}")
                return _EXIT_OK
            last_error = (result.stderr or result.stdout).strip()
            status = classify_gh_failure_text(last_error)

        if _AUTH_SIGNAL.search(last_error):
            print(f"Authentication failed: {last_error}", file=sys.stderr)
            return _EXIT_AUTH
        if status not in _RETRYABLE or attempt == MAX_ATTEMPTS:
            break

        delay = REFUSAL_BACKOFF_SECONDS[attempt - 1]
        print(
            f"Attempt {attempt}/{MAX_ATTEMPTS} refused ({status.value}); "
            f"retrying in {delay:.0f}s: {last_error}",
            file=sys.stderr,
        )
        wait(delay)

    # Report the attempts actually made, not the budget. A permanent refusal
    # breaks out on attempt 1, and claiming three would send the next reader
    # hunting for two retries that never happened.
    print(
        f"Could not request review from {reviewer} on PR #{pr_number} "
        f"after {attempt} attempt(s): {last_error}",
        file=sys.stderr,
    )
    return _EXIT_EXTERNAL


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.pull_request.isdigit():
        print(f"--pull-request must be a number: {args.pull_request}", file=sys.stderr)
        return _EXIT_CONFIG
    if "/" not in args.repo:
        print(f"--repo must be owner/name: {args.repo}", file=sys.stderr)
        return _EXIT_CONFIG

    code = assign_reviewer(args.repo, args.pull_request, args.reviewer)
    if code == _EXIT_EXTERNAL and args.tolerate_external:
        print(
            "::warning::Bot reviewer not assigned; the API refused the request "
            "for the whole retry budget. Not failing the job.",
        )
        return _EXIT_OK
    return code


if __name__ == "__main__":
    sys.exit(main())
