"""Post (or update) a velocity accelerator summary comment on a PR or issue.

Replaces the inline PowerShell block in velocity-accelerator.yml
(ADR-006: no logic in YAML). Reads OPPORTUNITIES_JSON, builds markdown,
finds an existing marker comment via paginated gh API, then creates or
updates the comment. No temp files are used.

EXIT CODES (ADR-035):
  0  - Success (including "nothing to post" and "no number" cases)
  2  - Configuration error (GITHUB_REPOSITORY not set)
  3  - gh API failure
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

EXIT_SUCCESS = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3


class CommentLookupError(Exception):
    """Raised when the GitHub API refuses or errors during comment lookup.

    Distinguishes a failed lookup (API 403, network error, bad JSON on a
    non-zero exit) from a successful lookup that found zero matches. The caller
    must not treat a failed lookup as "no comment exists" because that leads to
    duplicate posts (issue #4640).
    """

_MARKER = "<!-- VELOCITY-ACCELERATOR -->"


def build_summary(opportunities: list[dict[str, Any]]) -> str:
    if not opportunities:
        return ""

    lines = [f"## Velocity Accelerator: {len(opportunities)} Opportunities Detected\n"]
    for opp in opportunities:
        lines.append(f"### {opp.get('title', 'Opportunity')}")
        lines.append(f"- **Type**: `{opp.get('opportunity_type', '')}`")
        lines.append(f"- **Priority**: {opp.get('priority', '')}")
        if suggested := opp.get("suggested_agent", ""):
            lines.append(f"- **Suggested Agent**: {suggested}")
        lines.append(f"- {opp.get('description', '')}\n")
    lines.append(_MARKER)
    return "\n".join(lines)


def find_existing_comment(repo: str, number: str) -> int | None:
    """Return the id of the first marker-bearing comment, or None.

    Raises ``CommentLookupError`` when the API call fails (non-zero exit,
    empty stdout on the first page, or unparseable JSON on a non-zero exit).
    A successful query that finds zero matching comments returns None.
    The distinction matters: None means "safe to create a new comment";
    an exception means "do not mutate, report the failure" (issue #4640).
    """
    page = 1
    while True:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/issues/{number}/comments?per_page=100&page={page}",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise CommentLookupError(
                f"gh api returned exit {result.returncode} "
                f"(page {page}, stderr: {result.stderr!r})"
            )
        if not result.stdout:
            # A successful (rc=0) but empty stdout on page 1 means the API
            # returned nothing; on page >1 it means pagination ended.
            if page == 1:
                raise CommentLookupError(
                    "gh api returned exit 0 but empty stdout on first page"
                )
            break

        try:
            comments = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise CommentLookupError(
                f"Unparseable JSON on page {page}: {exc}"
            ) from exc

        if not comments:
            break

        for comment in comments:
            body = comment.get("body", "")
            if body and _MARKER in body:
                return int(comment["id"])

        if len(comments) < 100:
            break
        page += 1

    return None


def post_comment(repo: str, number: str, body: str, existing_id: int | None) -> int:
    if existing_id is not None:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{repo}/issues/comments/{existing_id}",
                "-X",
                "PATCH",
                "-f",
                f"body={body}",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            print(f"Updated existing velocity comment (id: {existing_id})")
        return result.returncode

    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/issues/{number}/comments",
            "-f",
            f"body={body}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        print(f"Created new velocity comment on #{number}")
    return result.returncode


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        print("ERROR: GITHUB_REPOSITORY not set", file=sys.stderr)
        return EXIT_CONFIG

    opportunities_json = os.environ.get("OPPORTUNITIES_JSON", "").strip()
    event_name = os.environ.get("EVENT_NAME", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "")

    try:
        opportunities = json.loads(opportunities_json) if opportunities_json else []
        if not isinstance(opportunities, list):
            opportunities = []
    except json.JSONDecodeError:
        opportunities = []

    summary = build_summary(opportunities)
    if not summary:
        print("No summary to post")
        return EXIT_SUCCESS

    number = pr_number if event_name == "pull_request" else issue_number
    if not number:
        print("No PR/issue number available; skipping comment post")
        return EXIT_SUCCESS

    existing_id: int | None
    try:
        existing_id = find_existing_comment(repo, number)
    except CommentLookupError as exc:
        # A failed lookup must not fall through to "post new comment" (issue
        # #4640). The safe default for a mutating action on lookup failure is
        # to do nothing and report the failure.
        print(f"ERROR: Comment lookup failed: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL

    rc = post_comment(repo, number, summary, existing_id)
    if rc != 0:
        print(f"ERROR: Comment post/update failed (exit {rc})", file=sys.stderr)
        return EXIT_EXTERNAL

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
