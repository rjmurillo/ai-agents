#!/usr/bin/env python3
"""Post a comment to a GitHub issue with idempotency support.

Replaces .claude/skills/github/scripts/issue/Post-IssueComment.ps1 (ADR-042).

Exit codes follow ADR-035:
    0 - Success (includes idempotent skip)
    1 - Invalid parameters / logic error
    2 - Config error (file not found)
    3 - External error (API failure)
    4 - Auth error (not authenticated, permission denied)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# sys.path setup so we can import scripts.github_core from repo root
# ---------------------------------------------------------------------------
_workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, _workspace)

from scripts.github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    get_issue_comments,
    resolve_repo_params,
    update_issue_comment,
)

# Regex for detecting 403 permission errors. Matches the pattern in
# scripts/github_core/api.py (_403_PATTERN) with negative lookarounds
# to prevent false positives on IDs like "Comment ID 4030".
_403_PATTERN = re.compile(
    r"((?<!\d)403(?!\d)|\bforbidden\b|Resource not accessible by integration)",
    re.IGNORECASE,
)

_403_GUIDANCE = """\
PERMISSION DENIED (403): Cannot post comment to issue #{issue} in {owner}/{repo}.

LIKELY CAUSES:
- GitHub Apps: Missing "issues": "write" permission in app manifest
- Workflow GITHUB_TOKEN: Add 'permissions: issues: write' to workflow YAML
- Fine-grained PAT: Enable 'Issues' repository permission (Read and Write)
- Classic PAT: Requires 'repo' scope for private repos or 'public_repo' for public repos
- Repository rules: May restrict who can comment

RAW ERROR: {error}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_github_output(pairs: dict[str, str]) -> None:
    """Append key=value pairs to $GITHUB_OUTPUT if the file exists."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    try:
        with open(output_path, "a", encoding="utf-8") as fh:
            for key, value in pairs.items():
                fh.write(f"{key}={value}\n")
    except OSError:
        print("WARNING: Failed to write GitHub Actions outputs", file=sys.stderr)


def save_failed_comment_artifact(
    owner: str,
    repo: str,
    issue: int,
    body: str,
    error: str,
) -> str | None:
    """Save the failed comment payload as a JSON artifact for manual recovery.

    Returns the artifact path on success, None on failure.
    """
    timestamp = datetime.now(tz=datetime.UTC).strftime("%Y-%m-%d-%H%M%S")

    # Determine repo root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        repo_root = result.stdout.strip() if result.returncode == 0 else os.getcwd()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        repo_root = os.getcwd()

    artifact_dir = Path(repo_root) / ".github" / "artifacts"
    artifact_path = artifact_dir / f"failed-comment-{timestamp}.json"

    payload = json.dumps(
        {
            "timestamp": datetime.now(tz=datetime.UTC).isoformat(),
            "owner": owner,
            "repo": repo,
            "issue": issue,
            "body": body,
            "error": error,
            "guidance": (
                f"Use 'gh api repos/{owner}/{repo}/issues/{issue}/comments"
                " -X POST -f body=@body.txt' to post manually"
            ),
        },
        indent=2,
    )

    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(payload, encoding="utf-8")
        print(f"Payload saved to: {artifact_path}", file=sys.stderr)
        return str(artifact_path)
    except OSError as exc:
        print(f"WARNING: Failed to save artifact: {exc}", file=sys.stderr)
        print("=== FAILED COMMENT PAYLOAD ===", file=sys.stderr)
        print(payload, file=sys.stderr)
        print("=== END PAYLOAD ===", file=sys.stderr)
        return None


def _prepend_marker(body: str, marker_html: str) -> str:
    """Prepend marker HTML comment to body if not already present."""
    if marker_html not in body:
        return f"{marker_html}\n\n{body}"
    return body


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Post a comment to a GitHub issue with idempotency support.",
    )
    parser.add_argument(
        "--owner",
        default="",
        help="Repository owner (inferred from git remote if omitted)",
    )
    parser.add_argument(
        "--repo",
        default="",
        help="Repository name (inferred from git remote if omitted)",
    )
    parser.add_argument("--issue", type=int, required=True, help="Issue number")

    body_group = parser.add_mutually_exclusive_group()
    body_group.add_argument("--body", default="", help="Comment body text")
    body_group.add_argument("--body-file", default="", help="Path to file containing comment body")

    parser.add_argument("--marker", default="", help="HTML comment marker for idempotency")
    parser.add_argument(
        "--update-if-exists",
        action="store_true",
        help="Update existing comment instead of skipping when marker found",
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # --- Auth ---
    assert_gh_authenticated()

    # --- Repo resolution ---
    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved["Owner"]
    repo = resolved["Repo"]
    issue: int = args.issue

    # --- Body resolution ---
    body: str = args.body
    if args.body_file:
        body_path = Path(args.body_file)
        if not body_path.exists():
            error_and_exit(f"Body file not found: {args.body_file}", 2)
        body = body_path.read_text(encoding="utf-8")

    if not body or not body.strip():
        error_and_exit("Body cannot be empty.", 1)

    # --- Marker / idempotency ---
    if args.marker:
        marker_html = f"<!-- {args.marker} -->"
        comments = get_issue_comments(owner, repo, issue)

        existing = None
        for comment in comments:
            if marker_html in comment.get("body", ""):
                existing = comment
                break

        if existing is not None:
            if args.update_if_exists:
                # Upsert: update existing comment
                print(f"Comment with marker '{args.marker}' exists. Updating...")
                body = _prepend_marker(body, marker_html)
                response = update_issue_comment(owner, repo, existing["id"], body)
                print(f"Updated comment on issue #{issue}")
                print(f"  URL: {response.get('html_url', 'N/A')}")
                print(f"Success: True, Issue: {issue}, CommentId: {response['id']}, Updated: True")
                write_github_output(
                    {
                        "success": "true",
                        "skipped": "false",
                        "updated": "true",
                        "issue": str(issue),
                        "comment_id": str(response["id"]),
                        "html_url": response.get("html_url", ""),
                        "updated_at": response.get("updated_at", ""),
                        "marker": args.marker,
                    }
                )
                return 0

            # Write-once idempotency: skip
            print(f"Comment with marker '{args.marker}' already exists. Skipping.")
            print(f"Success: True, Issue: {issue}, Marker: {args.marker}, Skipped: True")
            write_github_output(
                {
                    "success": "true",
                    "skipped": "true",
                    "issue": str(issue),
                    "marker": args.marker,
                }
            )
            return 0

        # No existing comment with marker, prepend marker and fall through to post
        body = _prepend_marker(body, marker_html)

    # --- Post new comment ---
    payload = json.dumps({"body": body})
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                f"repos/{owner}/{repo}/issues/{issue}/comments",
                "-X",
                "POST",
                "--input",
                "-",
            ],
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        error_and_exit("GitHub API request timed out while posting comment", 3)

    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()

        if _403_PATTERN.search(error_str):
            print(
                _403_GUIDANCE.format(issue=issue, owner=owner, repo=repo, error=error_str),
                file=sys.stderr,
            )
            artifact_path = save_failed_comment_artifact(owner, repo, issue, body, error_str)
            write_github_output(
                {
                    "success": "false",
                    "error": "PERMISSION_DENIED",
                    "status_code": "403",
                    **({"artifact_path": artifact_path} if artifact_path else {}),
                }
            )
            raise SystemExit(4)

        error_and_exit(f"Failed to post comment: {error_str}", 3)

    # Parse response
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError:
        # Comment was posted (gh exited 0) but response parse failed
        print(f"Posted comment to issue #{issue} (response parsing failed)", file=sys.stderr)
        write_github_output(
            {
                "success": "true",
                "skipped": "false",
                "issue": str(issue),
                "parse_error": "true",
            }
        )
        return 0

    print(f"Posted comment to issue #{issue}")
    print(f"  URL: {response.get('html_url', 'N/A')}")
    print(f"Success: True, Issue: {issue}, CommentId: {response['id']}, Skipped: False")

    outputs: dict[str, str] = {
        "success": "true",
        "skipped": "false",
        "issue": str(issue),
        "comment_id": str(response["id"]),
        "html_url": response.get("html_url", ""),
        "created_at": response.get("created_at", ""),
    }
    if args.marker:
        outputs["marker"] = args.marker
    write_github_output(outputs)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
