#!/usr/bin/env python3
"""Post a comment to a GitHub Issue with idempotency support.

If a marker exists in existing comments, behavior depends on --update-if-exists:
- Without flag: skips posting (write-once idempotency)
- With flag: updates existing comment (upsert behavior)

Exit codes follow ADR-035:
    0 - Success (includes idempotent skip)
    1 - Invalid parameters / logic error
    2 - File not found
    3 - External error (API failure)
    4 - Auth error (not authenticated, permission denied 403)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    resolve_repo_params,
    update_issue_comment,
)

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


def _write_github_output(outputs: dict[str, str]) -> None:
    """Write key=value pairs to GITHUB_OUTPUT if available."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    try:
        with open(output_file, "a", encoding="utf-8") as fh:
            for key, value in outputs.items():
                fh.write(f"{key}={value}\n")
    except OSError:
        pass


def _save_failed_comment_artifact(
    owner: str, repo: str, issue: int, body: str, error: str,
) -> str | None:
    """Save the failed comment payload as a JSON artifact for manual recovery."""
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y-%m-%d-%H%M%S")

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        repo_root = result.stdout.strip() if result.returncode == 0 else os.getcwd()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        repo_root = os.getcwd()

    artifact_dir = Path(repo_root) / ".github" / "artifacts"
    artifact_path = artifact_dir / f"failed-comment-{timestamp}.json"

    payload = json.dumps({
        "timestamp": now.isoformat(),
        "owner": owner,
        "repo": repo,
        "issue": issue,
        "body": body,
        "error": error,
        "guidance": (
            f"Use 'gh api repos/{owner}/{repo}/issues/{issue}/comments"
            " -X POST -f body=@body.txt' to post manually"
        ),
    }, indent=2)

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Post a comment to a GitHub issue with idempotency support.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
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


def main(argv: list[str] | None = None) -> int:  # noqa: C901 - faithful port of PS1 logic
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["Owner"], resolved["Repo"]
    issue: int = args.issue

    body: str = args.body
    if args.body_file:
        body_path = Path(args.body_file)
        if not body_path.exists():
            error_and_exit(f"Body file not found: {args.body_file}", 2)
        body = body_path.read_text(encoding="utf-8")

    if not body or not body.strip():
        error_and_exit("Body cannot be empty.", 1)

    # Marker / idempotency check
    if args.marker:
        marker_html = f"<!-- {args.marker} -->"

        comments_result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/issues/{issue}/comments"],
            capture_output=True, text=True, check=False,
        )

        if comments_result.returncode == 0:
            try:
                comments = json.loads(comments_result.stdout)
            except json.JSONDecodeError:
                comments = []

            existing = None
            for comment in comments:
                if marker_html in comment.get("body", ""):
                    existing = comment
                    break

            if existing is not None:
                if args.update_if_exists:
                    print(f"Comment with marker '{args.marker}' exists. Updating...")
                    body = _prepend_marker(body, marker_html)
                    response = update_issue_comment(owner, repo, existing["id"], body)
                    print(f"Updated comment on issue #{issue}")
                    print(json.dumps({
                        "success": True,
                        "issue": issue,
                        "comment_id": response["id"],
                        "updated": True,
                    }, indent=2))
                    _write_github_output({
                        "success": "true",
                        "skipped": "false",
                        "updated": "true",
                        "issue": str(issue),
                        "comment_id": str(response["id"]),
                        "html_url": response.get("html_url", ""),
                        "updated_at": response.get("updated_at", ""),
                        "marker": args.marker,
                    })
                    return 0

                print(f"Comment with marker '{args.marker}' already exists. Skipping.")
                print(json.dumps({
                    "success": True,
                    "issue": issue,
                    "marker": args.marker,
                    "skipped": True,
                }, indent=2))
                _write_github_output({
                    "success": "true",
                    "skipped": "true",
                    "issue": str(issue),
                    "marker": args.marker,
                })
                return 0

        body = _prepend_marker(body, marker_html)

    # Post new comment
    payload = json.dumps({"body": body})
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/issues/{issue}/comments",
            "-X", "POST",
            "--input", "-",
        ],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()

        if _403_PATTERN.search(error_str):
            print(
                _403_GUIDANCE.format(issue=issue, owner=owner, repo=repo, error=error_str),
                file=sys.stderr,
            )
            artifact_path = _save_failed_comment_artifact(owner, repo, issue, body, error_str)
            _write_github_output({
                "success": "false",
                "error": "PERMISSION_DENIED",
                "status_code": "403",
                **({"artifact_path": artifact_path} if artifact_path else {}),
            })
            raise SystemExit(4)

        error_and_exit(f"Failed to post comment: {error_str}", 3)

    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Posted comment to issue #{issue} (response parsing failed)", file=sys.stderr)
        _write_github_output({
            "success": "true",
            "skipped": "false",
            "issue": str(issue),
            "parse_error": "true",
        })
        return 0

    output = {
        "success": True,
        "issue": issue,
        "comment_id": response["id"],
        "skipped": False,
    }
    print(json.dumps(output, indent=2))

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
    _write_github_output(outputs)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
