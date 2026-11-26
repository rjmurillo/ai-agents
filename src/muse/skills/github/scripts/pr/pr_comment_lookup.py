"""Find an earlier identical conversation comment on a pull request.

``close_pr.py`` calls :func:`find_existing_comment` before it posts the closing
comment, so a retry after a failed close never leaves a duplicate. The pure
matching helpers live in ``pr_comment_dedupe.py``; this module owns the ``gh``
calls and maps every failure to exit 3 with the PR left open.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from skill_bootstrap import ensure_plugin_paths

# Same resolution order as close_pr.py, so a lib the caller found is found here.
ensure_plugin_paths(__file__, (".claude", "lib"))

from github_core.api import error_and_exit, sanitize_failure_detail
from pr_comment_dedupe import (
    LOOKUP_TIMEOUT_SECONDS,
    body_matches,
    first_bot_comment,
    first_by_author,
    flatten_pages,
    paginated_args,
)


def _lookup_failure(what: str, detail: str) -> str:
    return (
        f"Failed to {what} to check for a duplicate closing comment: {detail}. "
        "The PR was NOT closed and nothing was posted. "
        "Retry the same command once the API error clears."
    )


_INTEGRATION_DENIAL = "resource not accessible by integration"


def _authenticated_login() -> str | None:
    """Return the token owner's login, or None for a token that cannot call GET /user.

    A GitHub Actions installation token gets 403 "Resource not accessible by
    integration" from GET /user (see ``scripts/github_core/rate_limit.py``). That
    denial is not an API failure: the caller falls back to matching bot authors.
    Every other failure still exits 3.
    """
    try:
        result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        error_and_exit(_lookup_failure("read the authenticated user", "timed out after 30s"), 3)
    login = (result.stdout or "").strip()
    if result.returncode == 0 and login:
        return login
    raw = result.stderr or result.stdout or ""
    if result.returncode != 0 and _INTEGRATION_DENIAL in raw.casefold():
        return None
    detail = sanitize_failure_detail(raw, limit=400)
    error_and_exit(_lookup_failure("read the authenticated user", detail or "empty login"), 3)


def find_existing_comment(owner: str, repo: str, pr: int, comment: str) -> dict[str, Any] | None:
    """Return an identical-body conversation comment by the same author, else None.

    When GET /user is denied, any bot-authored comment with an identical body counts.
    """
    endpoint = f"repos/{owner}/{repo}/issues/{pr}/comments"
    what = f"read the comments of {owner}/{repo}#{pr}"
    try:
        result = subprocess.run(
            ["gh", "api", *paginated_args(endpoint)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=LOOKUP_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        error_and_exit(_lookup_failure(what, f"timed out after {LOOKUP_TIMEOUT_SECONDS}s"), 3)
    if result.returncode != 0:
        detail = sanitize_failure_detail(result.stderr or result.stdout, limit=400)
        error_and_exit(_lookup_failure(what, detail or "no output from gh"), 3)
    try:
        comments = flatten_pages(result.stdout)
    except ValueError as exc:
        error_and_exit(_lookup_failure(what, f"unreadable response ({exc})"), 3)
    same_body = body_matches(comments, comment)
    if not same_body:
        return None
    login = _authenticated_login()
    if login is None:
        print(
            "Note: GET /user is denied for this token; matching identical comments by bot "
            "authors instead of by login.",
            file=sys.stderr,
        )
        return first_bot_comment(same_body)
    return first_by_author(same_body, login)
