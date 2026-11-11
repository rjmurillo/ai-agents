"""Pure helpers that decide whether a comment was already posted.

``post_pr_comment_reply.py`` and ``new_pr_review_comment.py`` read the existing
comments before they post. If the same author already posted an identical body in
the same place, the script reports ``SKIP`` and posts nothing, so an agent that
retries a command never leaves a duplicate (agentskills.io, "Using scripts in
skills": "Agents may retry commands").

These helpers run no I/O. Each script owns its ``gh api`` call and maps failures
to its own envelope and exit code.

Pagination contract (``.claude/rules/lossless-queue-reads.md``): the read must see
every comment before it decides "no duplicate". ``gh api --paginate --slurp``
fails the whole call when any page fails, so a partial list never reaches
:func:`flatten_pages`. :func:`flatten_pages` also rejects any shape that is not a
list of pages, so a truncated or malformed read fails loud instead of reading as
"nothing posted yet".
"""

from __future__ import annotations

import json
from typing import Any

PAGE_SIZE = 100
LOOKUP_TIMEOUT_SECONDS = 120


def paginated_args(endpoint: str) -> list[str]:
    """Return the ``gh api`` arguments that fetch every page of ``endpoint``."""
    separator = "&" if "?" in endpoint else "?"
    return ["--paginate", "--slurp", f"{endpoint}{separator}per_page={PAGE_SIZE}"]


def flatten_pages(stdout: str) -> list[dict[str, Any]]:
    """Flatten ``gh api --paginate --slurp`` output into one list of comments.

    Raises ValueError when the output is not a list of lists of objects.
    """
    try:
        pages = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"output is not JSON: {exc.msg}") from None
    if not isinstance(pages, list):
        raise ValueError("expected a list of pages")
    comments: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, list):
            raise ValueError("expected every page to be a list")
        for item in page:
            if not isinstance(item, dict):
                raise ValueError("expected every comment to be an object")
            comments.append(item)
    return comments


def normalize_body(text: object) -> str:
    """Normalize a body for comparison.

    GitHub stores line endings as LF and trims the ends of a body, so a body
    posted as ``"a\\r\\nb\\n"`` reads back as ``"a\\nb"``. Compare on that form.
    """
    return str(text or "").replace("\r\n", "\n").strip()


def body_matches(comments: list[dict[str, Any]], body: str) -> list[dict[str, Any]]:
    """Return the comments whose body equals ``body`` after normalization."""
    wanted = normalize_body(body)
    return [c for c in comments if normalize_body(c.get("body")) == wanted]


def first_by_author(comments: list[dict[str, Any]], login: str) -> dict[str, Any] | None:
    """Return the first comment written by ``login`` (logins are case-insensitive)."""
    wanted = login.casefold()
    for comment in comments:
        user = comment.get("user")
        author = user.get("login") if isinstance(user, dict) else None
        if isinstance(author, str) and author.casefold() == wanted:
            return comment
    return None


def thread_comments(
    review_comments: list[dict[str, Any]], comment_id: int
) -> list[dict[str, Any]] | None:
    """Return every comment in the thread that holds ``comment_id``.

    A reply to any comment in a thread joins the thread root, so the thread is the
    root plus every comment whose ``in_reply_to_id`` is the root. Returns None
    when ``comment_id`` is not among ``review_comments``.
    """
    target = next((c for c in review_comments if c.get("id") == comment_id), None)
    if target is None:
        return None
    root_id = target.get("in_reply_to_id") or target.get("id")
    return [
        c for c in review_comments if c.get("id") == root_id or c.get("in_reply_to_id") == root_id
    ]


def comments_at_line(
    review_comments: list[dict[str, Any]], path: str, line: int, side: str
) -> list[dict[str, Any]]:
    """Return top-level review comments on ``path`` at ``line`` on ``side``.

    A comment whose line moved with a later push reports ``line`` as null and keeps
    the line it was written on in ``original_line``.
    """
    matched = []
    for comment in review_comments:
        if comment.get("in_reply_to_id") or comment.get("path") != path:
            continue
        if (comment.get("side") or "RIGHT") != side:
            continue
        current = comment.get("line")
        shown = current if current is not None else comment.get("original_line")
        if shown == line:
            matched.append(comment)
    return matched
