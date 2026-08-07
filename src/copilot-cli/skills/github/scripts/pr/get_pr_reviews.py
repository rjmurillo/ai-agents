#!/usr/bin/env python3
"""Fetch submitted reviews for a GitHub Pull Request.

Returns each review's id, node_id, author, state, body, submitted timestamp,
and URL. Paginates via REST so large review threads do not truncate.

Issue #4378: ``get_pr_reviewers.py`` discards review state and body, so an
agent cannot read APPROVED/REQUEST_CHANGES verdicts or their accompanying
text through the skill surface. This script fills that gap.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Not found
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

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

_SCRIPT = "get_pr_reviews.py"

# Canonical alias map for known bot identities.
# Maps each observed alias to the canonical name kept in output.
# The raw alias is preserved in the ``aliases`` list for audit.
_BOT_ALIASES: dict[str, str] = {
    "copilot-pull-request-reviewer": "Copilot",
    "github-actions": "github-actions[bot]",
}

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
        description="Fetch submitted reviews for a GitHub Pull Request.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    add_output_format_arg(parser)
    return parser


def _is_auth_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _AUTH_ERROR_MARKERS)


def _exit_code_for(message: str, *, not_found: bool) -> tuple[int, str]:
    if not_found:
        return 2, "NotFound"
    if _is_auth_error(message):
        return 4, "AuthError"
    return 3, "ApiError"


def _fetch_reviews(
    owner: str, repo: str, pr: int, fmt: str,
) -> list[dict[str, object]]:
    """Page through the PR's reviews via REST. Raises SystemExit on error."""
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/pulls/{pr}/reviews?per_page=100",
            "--paginate",
            "--slurp",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        not_found = "not found" in error_str.lower() or "Could not resolve" in error_str
        code, error_type = _exit_code_for(error_str, not_found=not_found)
        write_skill_error(
            f"Failed to fetch reviews for PR #{pr}: {error_str}",
            code,
            error_type=error_type,
            output_format=fmt,
            script_name=_SCRIPT,
            extra={"pull_request": pr},
        )
        raise SystemExit(code)
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        write_skill_error(
            f"Failed to parse reviews for PR #{pr}: {exc}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name=_SCRIPT,
            extra={"pull_request": pr},
        )
        raise SystemExit(3) from exc
    # --slurp wraps each page array in an outer list; flatten one level.
    pages = payload if isinstance(payload, list) else [payload]
    reviews: list[dict[str, object]] = []
    for page in pages:
        items = page if isinstance(page, list) else [page]
        for item in items:
            if isinstance(item, dict):
                reviews.append(item)
    return reviews


def _canonicalize_login(login: str) -> tuple[str, list[str]]:
    """Return (canonical_login, aliases) for a reviewer login.

    Known bot aliases are normalized to a single canonical name to prevent
    the same actor appearing as multiple distinct reviewers (issue #4378).
    The raw alias is preserved in the returned list for audit.
    """
    canonical = _BOT_ALIASES.get(login, login)
    aliases = [login] if canonical != login else []
    return canonical, aliases


def _normalize(item: dict[str, object]) -> dict[str, object]:
    user = item.get("user")
    raw_login = user.get("login") if isinstance(user, dict) else ""
    canonical, aliases = _canonicalize_login(raw_login or "")
    return {
        "id": item.get("id"),
        "node_id": item.get("node_id"),
        "author": canonical,
        "aliases": aliases,
        "state": item.get("state"),
        "body": item.get("body") or "",
        "submittedAt": item.get("submitted_at"),
        "url": item.get("html_url"),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)
    pr: int = args.pull_request

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    raw = _fetch_reviews(owner, repo, pr, fmt)
    reviews = [_normalize(r) for r in raw]

    data = {
        "pull_request": pr,
        "owner": owner,
        "repo": repo,
        "count": len(reviews),
        "reviews": reviews,
    }
    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"PR #{pr}: {len(reviews)} review(s)",
        status="PASS",
        script_name=_SCRIPT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
