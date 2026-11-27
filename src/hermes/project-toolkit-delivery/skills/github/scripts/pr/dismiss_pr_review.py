#!/usr/bin/env python3
"""Dismiss a stale CHANGES_REQUESTED review on a pull request.

This is the execution path the ``detect_stale_bot_review.py`` handoff points a
human at. It replaces the raw ``gh api -X PUT .../dismissals`` paste with
precondition checks, structured output, and an audit record:

- The review must exist and be in ``CHANGES_REQUESTED`` state. An already
  dismissed review is a no-op success; any other state is refused.
- Unresolved review threads block dismissal by default: the script counts
  unresolved threads through one GraphQL query and refuses while any remain.
  When the session's GraphQL transport is refused or exhausted, the check
  cannot run and the script exits 3; ``--skip-thread-check`` is the explicit,
  audit-recorded escape for that case, never the default.
- ``--message`` is required: GitHub records it on the dismissal, and a blank
  reason is no reason at all.
- The review's commit is compared with the current head and reported in the
  output. A review on the current head can still be dismissed when its
  threads are all resolved (a bot that never re-reviews), but the output
  says so plainly.

The agent does not decide to dismiss. Who runs this script is policy; what
the script enforces is preconditions. Detection stays with
``detect_stale_bot_review.py``, which never dismisses anything.

Exit codes follow ADR-035:
    0 - Success (or no-op)
    1 - Logic or validation error (wrong state, unresolved threads)
    2 - Usage or configuration error
    3 - External service or API error, or the PR or review was not found
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from skill_bootstrap import ensure_plugin_paths

ensure_plugin_paths(__file__, (".claude", "lib"))

from github_core.api import (
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "dismiss_pr_review.py"

_THREADS_QUERY = """\
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      headRefOid
      reviewThreads(first: 100) {
        nodes { isResolved }
        pageInfo { hasNextPage }
      }
    }
  }
}"""


def _run_gh(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        input=input_text,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def _fail_message(result: subprocess.CompletedProcess[str], what: str) -> str:
    return (
        result.stderr.strip()
        or result.stdout.strip()
        or f"{what} failed with no stderr or stdout output"
    )


def fetch_review(owner: str, repo: str, pr: int, review_id: int) -> dict | None:
    """Return the review payload, or None when it does not exist."""
    result = _run_gh(["api", f"repos/{owner}/{repo}/pulls/{pr}/reviews/{review_id}"])
    if result.returncode != 0:
        detail = _fail_message(result, f"gh api review {review_id}")
        if "404" in detail or "Not Found" in detail:
            return None
        raise RuntimeError(detail)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to decode review response: {exc}") from exc


def fetch_pr_head(owner: str, repo: str, pr: int) -> str:
    result = _run_gh(["api", f"repos/{owner}/{repo}/pulls/{pr}", "--jq", ".head.sha"])
    if result.returncode != 0:
        raise RuntimeError(_fail_message(result, f"gh api pulls/{pr}"))
    return result.stdout.strip()


def count_unresolved_threads(owner: str, repo: str, pr: int) -> tuple[int | None, str]:
    """Return (unresolved count, error).

    Count is None when the query could not run or the thread list paginates
    past the first page, because a capped scan is not evidence.
    """
    try:
        result = _run_gh(
            [
                "api",
                "graphql",
                "-F",
                "query=@-",
                "-f",
                f"owner={owner}",
                "-f",
                f"repo={repo}",
                "-F",
                f"pr={pr}",
            ],
            input_text=_THREADS_QUERY,
        )
    except subprocess.TimeoutExpired:
        return None, "gh api graphql reviewThreads timed out"
    if result.returncode != 0:
        return None, _fail_message(result, "gh api graphql reviewThreads")
    try:
        payload = json.loads(result.stdout)
        pull = payload["data"]["repository"]["pullRequest"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return None, f"Failed to decode reviewThreads response: {exc}"
    if pull is None:
        return None, f"PR #{pr} not found in GraphQL response"
    threads = pull.get("reviewThreads")
    if not isinstance(threads, dict):
        return None, "reviewThreads missing in GraphQL response"
    if threads.get("pageInfo", {}).get("hasNextPage"):
        return None, "review threads paginate past 100; refusing to count from a partial scan"
    unresolved = sum(1 for node in threads.get("nodes", []) if not node.get("isResolved"))
    head = str(pull.get("headRefOid") or "")
    return unresolved, "" if head else "head SHA missing in GraphQL response"


def dismiss_review(owner: str, repo: str, pr: int, review_id: int, message: str) -> None:
    result = _run_gh(
        [
            "api",
            "-X",
            "PUT",
            f"repos/{owner}/{repo}/pulls/{pr}/reviews/{review_id}/dismissals",
            "--input",
            "-",
        ],
        input_text=json.dumps({"event": "DISMISS", "message": message}),
    )
    if result.returncode != 0:
        raise RuntimeError(_fail_message(result, "dismissal request"))


_HELP_EPILOG = """\
examples:
  %(prog)s --pull-request 123 --review-id 456789 --message "Threads resolved; review predates fixes"
  %(prog)s --pull-request 123 --review-id 456789 --message "..." --dry-run

exit codes:
  0  success (or no-op)
  1  logic or validation error (wrong review state, unresolved threads)
  2  usage or configuration error
  3  external service or API error, or the PR or review was not found
  4  auth error
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Dismiss a stale CHANGES_REQUESTED review with precondition checks.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--owner", default="")
    p.add_argument("--repo", default="")
    p.add_argument("--pull-request", type=int, required=True)
    p.add_argument("--review-id", type=int, required=True)
    p.add_argument(
        "--message",
        required=True,
        help="Dismissal reason, recorded on the review. Required and non-blank.",
    )
    p.add_argument(
        "--skip-thread-check",
        action="store_true",
        help=(
            "Dismiss without the unresolved-thread check. Recorded in the audit "
            "output. Intended only for sessions whose GraphQL transport is refused "
            "or exhausted, after the caller verified resolution another way."
        ),
    )
    p.add_argument("--dry-run", action="store_true")
    add_output_format_arg(p)
    return p


def _thread_gate(
    args: argparse.Namespace,
    owner: str,
    repo: str,
    pr: int,
    review_id: int,
    fmt: str,
) -> tuple[int | None, int]:
    """Run the unresolved-thread gate. Return (count, exit code).

    Exit code 0 means dismissal may proceed. A nonzero code means the error
    output is already written and main returns it unchanged.
    """
    if args.skip_thread_check:
        return None, 0
    unresolved, thread_error = count_unresolved_threads(owner, repo, pr)
    if unresolved is None:
        write_skill_error(
            f"Unresolved-thread check could not run: {thread_error}. "
            "Verify resolution another way and re-run with --skip-thread-check, "
            "or do not dismiss.",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
        )
        return 0, 3
    if unresolved:
        write_skill_error(
            f"PR #{pr} still has {unresolved} unresolved review thread(s); "
            "resolve them before dismissing the review",
            1,
            error_type="VerificationFailed",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
            extra={
                "pull_request": pr,
                "review_id": review_id,
                "unresolved_threads": unresolved,
            },
        )
        return 0, 1
    return unresolved, 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    pr = args.pull_request
    review_id = args.review_id

    if not args.message.strip():
        write_skill_error(
            "--message must not be blank; GitHub records it on the dismissal",
            2,
            error_type="InvalidParams",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
        )
        return 2

    try:
        review = fetch_review(owner, repo, pr, review_id)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        write_skill_error(
            str(exc), 3, error_type="ApiError", output_format=fmt, script_name=_SCRIPT_NAME
        )
        return 3

    if review is None:
        write_skill_error(
            f"Review {review_id} on PR #{pr} not found",
            3,
            error_type="NotFound",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
        )
        return 3

    state = str(review.get("state") or "")
    audit: dict[str, object] = {
        "actor": "human-directed",
        "target": f"{owner}/{repo}#{pr} review {review_id}",
        "action": "dismiss_review",
        "thread_check": "skipped" if args.skip_thread_check else "enforced",
    }

    if state == "DISMISSED":
        write_skill_output(
            {
                "Success": True,
                "pull_request": pr,
                "review_id": review_id,
                "action": "no-op",
                "message": "Review already dismissed",
                "audit": {**audit, "result": "no-op"},
            },
            output_format=fmt,
            human_summary=f"PR #{pr}: review {review_id} already dismissed",
            status="PASS",
            script_name=_SCRIPT_NAME,
        )
        return 0

    if state != "CHANGES_REQUESTED":
        write_skill_error(
            f"Review {review_id} is {state or 'in an unknown state'}, not CHANGES_REQUESTED; "
            "dismissal exists to clear a blocking review",
            1,
            error_type="VerificationFailed",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
            extra={"pull_request": pr, "review_id": review_id, "state": state},
        )
        return 1

    unresolved, thread_gate = _thread_gate(args, owner, repo, pr, review_id, fmt)
    if thread_gate:
        return thread_gate

    try:
        head_sha = fetch_pr_head(owner, repo, pr)
    except (RuntimeError, subprocess.SubprocessError, OSError):
        head_sha = ""
    review_commit = str(review.get("commit_id") or "")
    # Unknown head is unknown, not false: a failed head read must not read
    # as evidence the review is stale.
    on_current_head = None if not head_sha else review_commit == head_sha

    facts = {
        "pull_request": pr,
        "review_id": review_id,
        "review_commit": review_commit,
        "head_sha": head_sha,
        "review_on_current_head": on_current_head,
        "unresolved_threads": unresolved,
    }

    if args.dry_run:
        write_skill_output(
            {
                "Success": True,
                **facts,
                "action": "dry-run",
                "message": "Would dismiss the review",
                "audit": {**audit, "result": "dry-run"},
            },
            output_format=fmt,
            human_summary=f"PR #{pr}: dry-run, would dismiss review {review_id}",
            status="PASS",
            script_name=_SCRIPT_NAME,
        )
        return 0

    try:
        dismiss_review(owner, repo, pr, review_id, args.message)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        write_skill_error(
            str(exc), 3, error_type="ApiError", output_format=fmt, script_name=_SCRIPT_NAME
        )
        return 3

    write_skill_output(
        {
            "Success": True,
            **facts,
            "action": "dismissed",
            "dismissal_message": args.message,
            "audit": {
                **audit,
                "result": "dismissed",
                "rollback": "none; a dismissed review cannot be un-dismissed, "
                "but the reviewer can be re-requested",
                "residual_risk": "findings fixed after the review are verified by the "
                "human who ran the dismissal, not by this script",
            },
        },
        output_format=fmt,
        human_summary=f"PR #{pr}: review {review_id} dismissed",
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
