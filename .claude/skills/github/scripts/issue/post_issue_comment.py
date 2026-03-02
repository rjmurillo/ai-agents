#!/usr/bin/env python3
"""Post a comment to a GitHub Issue with idempotency support.

Posts comments to issues with optional marker for idempotency.
If marker exists in existing comments:
  - Without --update-if-exists: skips posting (write-once idempotency)
  - With --update-if-exists: updates existing comment (upsert behavior)

Exit codes (ADR-035):
    0 = Success (including skip due to marker)
    1 = Invalid parameters
    2 = File not found
    3 = API error
    4 = Auth error (not authenticated or permission denied 403)
"""

import argparse
import json
import os
import re
import subprocess
import sys

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    _run_gh,
    assert_gh_authenticated,
    resolve_repo_params,
    write_error_and_exit,
)


def _ensure_marker_in_body(body: str, marker_html: str) -> str:
    """Prepend marker to body if not already present."""
    if marker_html not in body:
        return f"{marker_html}\n\n{body}"
    return body


def _find_existing_marker_comment(
    owner: str, repo: str, issue: int, marker_html: str,
) -> dict | None:
    """Find existing comment with the given marker."""
    result = _run_gh(
        "api", f"repos/{owner}/{repo}/issues/{issue}/comments",
        check=False,
    )
    if result.returncode != 0:
        return None

    try:
        comments = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    escaped = re.escape(marker_html)
    for comment in comments:
        if re.search(escaped, comment.get("body", "")):
            return comment
    return None


def _update_comment(owner: str, repo: str, comment_id: int, body: str) -> dict:
    """Update an existing issue comment."""
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/issues/comments/{comment_id}",
            "-X", "PATCH", "-f", f"body={body}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        write_error_and_exit(f"Failed to update comment: {result.stderr}", 3)
    return json.loads(result.stdout)


def _detect_permission_error(error_text: str) -> bool:
    """Check if error indicates a 403 permission denied."""
    patterns = ["HTTP 403", "status.*403", "403",
                "Resource not accessible by integration", "forbidden"]
    for pattern in patterns:
        if re.search(pattern, error_text, re.IGNORECASE):
            return True
    return False


def post_issue_comment(
    owner: str,
    repo: str,
    issue: int,
    body: str,
    marker: str = "",
    update_if_exists: bool = False,
) -> dict:
    """Post or update a comment on a GitHub issue.

    Args:
        owner: Repository owner.
        repo: Repository name.
        issue: Issue number.
        body: Comment body text.
        marker: Optional idempotency marker.
        update_if_exists: Update existing comment if marker found.

    Returns:
        Dict with operation result.
    """
    marker_html = f"<!-- {marker} -->" if marker else ""

    if marker:
        existing = _find_existing_marker_comment(owner, repo, issue, marker_html)
        if existing:
            if update_if_exists:
                updated_body = _ensure_marker_in_body(body, marker_html)
                response = _update_comment(
                    owner, repo, existing["id"], updated_body
                )
                return {
                    "Success": True,
                    "Issue": issue,
                    "CommentId": response["id"],
                    "HtmlUrl": response.get("html_url", ""),
                    "Skipped": False,
                    "Updated": True,
                    "Marker": marker,
                }
            return {
                "Success": True,
                "Issue": issue,
                "CommentId": existing["id"],
                "Skipped": True,
                "Updated": False,
                "Marker": marker,
            }
        body = _ensure_marker_in_body(body, marker_html)

    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/issues/{issue}/comments",
            "-X", "POST", "-f", f"body={body}",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_text = result.stderr or result.stdout
        if _detect_permission_error(error_text):
            write_error_and_exit(
                f"PERMISSION DENIED (403): Cannot post comment to "
                f"issue #{issue} in {owner}/{repo}. "
                f"Check token permissions.", 4
            )
        write_error_and_exit(f"Failed to post comment: {error_text}", 3)

    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "Success": True,
            "Issue": issue,
            "CommentId": None,
            "Skipped": False,
            "Updated": False,
            "ParseError": True,
        }

    return {
        "Success": True,
        "Issue": issue,
        "CommentId": response.get("id"),
        "HtmlUrl": response.get("html_url", ""),
        "Skipped": False,
        "Updated": False,
        "Marker": marker if marker else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post a comment to a GitHub issue"
    )
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument("--body", help="Comment body text")
    parser.add_argument("--body-file", help="Path to file containing comment")
    parser.add_argument(
        "--marker", default="",
        help="HTML comment marker for idempotency",
    )
    parser.add_argument(
        "--update-if-exists", action="store_true",
        help="Update existing comment if marker found",
    )
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    body = args.body or ""
    if args.body_file:
        if not os.path.isfile(args.body_file):
            write_error_and_exit(f"Body file not found: {args.body_file}", 2)
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read()

    if not body.strip():
        write_error_and_exit("Body cannot be empty.", 1)

    output = post_issue_comment(
        resolved["owner"], resolved["repo"], args.issue,
        body, args.marker, args.update_if_exists,
    )

    print(json.dumps(output, indent=2))
    if output.get("Skipped"):
        print(
            f"Comment with marker '{args.marker}' already exists. Skipping.",
            file=sys.stderr,
        )
    elif output.get("Updated"):
        print(f"Updated comment on issue #{args.issue}", file=sys.stderr)
    else:
        print(f"Posted comment to issue #{args.issue}", file=sys.stderr)


if __name__ == "__main__":
    main()
