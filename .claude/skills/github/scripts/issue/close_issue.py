#!/usr/bin/env python3
"""Close a GitHub Issue with an optional closing comment.

Posts an optional comment (from ``--comment`` or ``--comment-file``) and then
closes the issue via ``gh issue close --reason``. Emits the standard ADR-056
skill output envelope ({Success, Data, Error, Metadata}).

Exit codes follow ADR-035:
    0 - Success (issue closed, or already closed)
    1 - Invalid parameters / logic error
    2 - File not found / config error
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

# gh issue close --reason accepts exactly these two values. "not planned" is the
# spelling gh expects (with a space), so we pass the value through verbatim.
_VALID_REASONS = ("completed", "not planned")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Close a GitHub Issue with an optional closing comment.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument(
        "--reason",
        choices=list(_VALID_REASONS),
        default="completed",
        help="Close reason: 'completed' (default) or 'not planned'.",
    )

    comment_group = parser.add_mutually_exclusive_group()
    comment_group.add_argument(
        "--comment", default="", help="Closing comment body text",
    )
    comment_group.add_argument(
        "--comment-file", default="", help="Path to a file containing the comment body",
    )

    add_output_format_arg(parser)
    return parser


def _comment_base_dir() -> Path:
    """Return the directory that comment files must stay under."""
    workspace = os.environ.get("GITHUB_WORKSPACE", "").strip()
    return Path(workspace or os.getcwd()).resolve()


def _resolve_comment_file(comment_file: str, fmt: str) -> Path:
    base_dir = _comment_base_dir()
    raw_path = Path(comment_file)
    path = raw_path if raw_path.is_absolute() else base_dir / raw_path
    resolved = path.resolve()
    if not resolved.is_relative_to(base_dir):
        write_skill_error(
            f"Comment file must stay under {base_dir}: {comment_file}",
            2,
            error_type="InvalidParams",
            output_format=fmt,
            script_name="close_issue.py",
            extra={"issue": None},
        )
        raise SystemExit(2)
    if not resolved.is_file():
        write_skill_error(
            f"Comment file not found: {comment_file}",
            2,
            error_type="NotFound",
            output_format=fmt,
            script_name="close_issue.py",
            extra={"issue": None},
        )
        raise SystemExit(2)
    return resolved


def _resolve_comment(comment: str, comment_file: str, fmt: str) -> str:
    """Return the closing comment body, reading the file when one is given.

    Exits with code 2 (config error) when the comment file is missing. Returns
    an empty string when no comment was requested.
    """
    if comment_file:
        path = _resolve_comment_file(comment_file, fmt)
        return path.read_text(encoding="utf-8")
    return comment


def _get_issue_state(owner: str, repo: str, issue: int, fmt: str) -> str:
    """Return the issue state from GitHub, lowercased."""
    result = subprocess.run(
        [
            "gh", "issue", "view", str(issue),
            "--repo", f"{owner}/{repo}",
            "--json", "state",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        write_skill_error(
            f"Failed to get issue #{issue}: {error_str}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="close_issue.py",
            extra={"issue": issue},
        )
        raise SystemExit(3)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        write_skill_error(
            f"Failed to parse issue #{issue} state: {exc}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="close_issue.py",
            extra={"issue": issue},
        )
        raise SystemExit(3) from exc
    return str(payload.get("state", "")).lower()


def _post_comment(owner: str, repo: str, issue: int, body: str, fmt: str) -> None:
    """Post a closing comment via gh api. Exits with code 3 on failure."""
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
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        write_skill_error(
            f"Failed to post closing comment: {error_str}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="close_issue.py",
            extra={"issue": issue},
        )
        raise SystemExit(3)


def _close_issue(owner: str, repo: str, issue: int, reason: str) -> subprocess.CompletedProcess[str]:
    """Run gh issue close with the given reason. Returns the completed process."""
    return subprocess.run(
        [
            "gh", "issue", "close", str(issue),
            "--repo", f"{owner}/{repo}",
            "--reason", reason,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    issue: int = args.issue

    state = _get_issue_state(owner, repo, issue, fmt)
    if state == "closed":
        data = {
            "issue": issue,
            "owner": owner,
            "repo": repo,
            "state": "closed",
            "reason": args.reason,
            "commented": False,
            "action": "already_closed",
        }
        write_skill_output(
            data,
            output_format=fmt,
            human_summary=f"Issue #{issue} is already closed",
            status="PASS",
            script_name="close_issue.py",
        )
        return 0

    body = _resolve_comment(args.comment, args.comment_file, fmt)
    commented = bool(body and body.strip())
    if commented:
        _post_comment(owner, repo, issue, body, fmt)

    result = _close_issue(owner, repo, issue, args.reason)
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        write_skill_error(
            f"Failed to close issue #{issue}: {error_str}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="close_issue.py",
            extra={"issue": issue},
        )
        return 3

    data = {
        "issue": issue,
        "owner": owner,
        "repo": repo,
        "state": "closed",
        "reason": args.reason,
        "commented": commented,
        "action": "closed",
    }
    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"Closed issue #{issue} as '{args.reason}'",
        status="PASS",
        script_name="close_issue.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
