#!/usr/bin/env python3
"""Reopen a closed GitHub Issue with an optional comment.

Reopens the issue via ``gh issue reopen`` and posts an optional comment from
``--comment`` or ``--comment-file`` (for example, the reason a prior close was
reversed). On retry, an already-open issue can still receive a missing comment
without duplicating an existing one. Emits the standard ADR-056 skill output
envelope ({Success, Data, Error, Metadata}).

The inverse of ``close_issue.py``; the helper structure mirrors that script so
the two stay symmetric. Triage that closes an issue can be reversed through the
skill layer instead of falling back to raw ``gh`` (Issue #2475).

Exit codes follow ADR-035:
    0 - Success (issue reopened, or already open)
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

_SCRIPT = "reopen_issue.py"
_AUTH_ERROR_MARKERS = (
    "credential",
    "not logged in",
    "bad credentials",
    "could not authenticate",
    "authentication",
    "requires authentication",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reopen a closed GitHub Issue with an optional comment.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")

    comment_group = parser.add_mutually_exclusive_group()
    comment_group.add_argument(
        "--comment",
        default="",
        help="Comment body text to post on reopen",
    )
    comment_group.add_argument(
        "--comment-file",
        default="",
        help="Path to a file containing the comment body",
    )

    add_output_format_arg(parser)
    return parser


def _comment_base_dir() -> Path:
    """Return the directory that comment files must stay under (CWE-22 guard)."""
    workspace = os.environ.get("GITHUB_WORKSPACE", "").strip()
    if workspace:
        return Path(workspace).expanduser().resolve()
    return Path.cwd().resolve()


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
            script_name=_SCRIPT,
            extra={"issue": None},
        )
        raise SystemExit(2)
    if not resolved.is_file():
        write_skill_error(
            f"Comment file not found: {comment_file}",
            2,
            error_type="NotFound",
            output_format=fmt,
            script_name=_SCRIPT,
            extra={"issue": None},
        )
        raise SystemExit(2)
    return resolved


def _resolve_comment(comment: str, comment_file: str, fmt: str) -> str:
    """Return the comment body, reading the file when one is given."""
    if comment_file:
        path = _resolve_comment_file(comment_file, fmt)
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            write_skill_error(
                f"Failed to read comment file {comment_file}: {exc}",
                2,
                error_type="InvalidParams",
                output_format=fmt,
                script_name=_SCRIPT,
                extra={"issue": None},
            )
            raise SystemExit(2) from exc
    return comment


def _is_auth_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _AUTH_ERROR_MARKERS)


def _write_subprocess_error(message: str, issue: int, fmt: str, *, not_found: bool = False) -> int:
    if not_found:
        code = 2
        error_type = "NotFound"
    elif _is_auth_error(message):
        code = 4
        error_type = "AuthError"
    else:
        code = 3
        error_type = "ApiError"
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=fmt,
        script_name=_SCRIPT,
        extra={"issue": issue},
    )
    return code


def _get_issue_state(owner: str, repo: str, issue: int, fmt: str) -> str:
    """Return the issue state from GitHub, lowercased."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "view",
            str(issue),
            "--repo",
            f"{owner}/{repo}",
            "--json",
            "state",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        code = _write_subprocess_error(
            f"Failed to get issue #{issue}: {error_str}",
            issue,
            fmt,
            not_found=("Could not resolve" in error_str or "not found" in error_str.lower()),
        )
        raise SystemExit(code)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        write_skill_error(
            f"Failed to parse issue #{issue} state: {exc}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name=_SCRIPT,
            extra={"issue": issue},
        )
        raise SystemExit(3) from exc
    if not isinstance(payload, dict):
        return ""
    state = payload.get("state")
    return "" if state is None else str(state).lower()


def _post_comment(owner: str, repo: str, issue: int, body: str, fmt: str) -> None:
    """Post a comment via gh api. Exits with code 3 on failure."""
    payload = json.dumps({"body": body})
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
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        code = _write_subprocess_error(
            f"Failed to post reopen comment: {error_str}",
            issue,
            fmt,
        )
        raise SystemExit(code)


def _comment_bodies(payload: object) -> list[str]:
    if isinstance(payload, dict):
        return _comment_bodies(payload.get("comments"))
    if not isinstance(payload, list):
        return []
    bodies: list[str] = []
    for item in payload:
        if isinstance(item, list):
            bodies.extend(_comment_bodies(item))
        elif isinstance(item, dict) and isinstance(item.get("body"), str):
            bodies.append(item["body"])
    return bodies


def _comment_exists(owner: str, repo: str, issue: int, body: str, fmt: str) -> bool:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/issues/{issue}/comments?per_page=100",
            "--paginate",
            "--slurp",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        code = _write_subprocess_error(
            f"Failed to inspect issue #{issue} comments: {error_str}",
            issue,
            fmt,
        )
        raise SystemExit(code)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        write_skill_error(
            f"Failed to parse issue #{issue} comments: {exc}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name=_SCRIPT,
            extra={"issue": issue},
        )
        raise SystemExit(3) from exc
    return body in _comment_bodies(payload)


def _reopen_issue(owner: str, repo: str, issue: int) -> subprocess.CompletedProcess[str]:
    """Run gh issue reopen. Returns the completed process."""
    return subprocess.run(
        [
            "gh",
            "issue",
            "reopen",
            str(issue),
            "--repo",
            f"{owner}/{repo}",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)
    body = _resolve_comment(args.comment, args.comment_file, fmt)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    issue: int = args.issue

    state = _get_issue_state(owner, repo, issue, fmt)
    if state == "open":
        # Idempotent: already open. Still post a missing comment if requested.
        commented = False
        comment_already_present = False
        if body and body.strip():
            comment_already_present = _comment_exists(owner, repo, issue, body, fmt)
            if not comment_already_present:
                _post_comment(owner, repo, issue, body, fmt)
                commented = True
        data = {
            "issue": issue,
            "owner": owner,
            "repo": repo,
            "state": "open",
            "commented": commented,
            "commentAlreadyPresent": comment_already_present,
            "action": "already_open",
        }
        write_skill_output(
            data,
            output_format=fmt,
            human_summary=f"Issue #{issue} is already open",
            status="PASS",
            script_name=_SCRIPT,
        )
        return 0

    result = _reopen_issue(owner, repo, issue)
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        code = _write_subprocess_error(
            f"Failed to reopen issue #{issue}: {error_str}",
            issue,
            fmt,
        )
        return code

    commented = bool(body and body.strip())
    if commented:
        _post_comment(owner, repo, issue, body, fmt)

    data = {
        "issue": issue,
        "owner": owner,
        "repo": repo,
        "state": "open",
        "commented": commented,
        "action": "reopened",
    }
    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"Reopened issue #{issue}",
        status="PASS",
        script_name=_SCRIPT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
