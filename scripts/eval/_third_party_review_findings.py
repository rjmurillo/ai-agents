"""Pure extraction of third-party bot review threads from a mined dump.

No I/O. Input is the pull request list ``_third_party_review_fetch`` returns.
"""

from __future__ import annotations

import re
from typing import Any

# Reviewer bots outside this repository's own agent pipeline. Logins are
# matched case-insensitively with any `[bot]` suffix removed.
THIRD_PARTY_BOTS: dict[str, str] = {
    "coderabbitai": "coderabbit",
    "cursor": "cursor",
    "devin-ai-integration": "devin",
    "copilot-pull-request-reviewer": "copilot",
    "copilot": "copilot",
    "github-copilot": "copilot",
    "gemini-code-assist": "gemini",
    "chatgpt-codex-connector": "codex",
    "sourcery-ai": "sourcery",
    "qodo-merge-pro": "qodo",
    "greptile-apps": "greptile",
    "github-advanced-security": "codeql",
}
# The Semgrep app's login carries the installing account, as `semgrep-code-<owner>`.
SEMGREP_PREFIX = "semgrep-code-"

_BOT_SUFFIX = re.compile(r"\[bot\]$", re.IGNORECASE)


def bot_name(login: str | None) -> str | None:
    """The short reviewer name for a third-party bot login, else None."""
    if not login:
        return None
    key = _BOT_SUFFIX.sub("", login).lower()
    if key.startswith(SEMGREP_PREFIX):
        return "semgrep"
    return THIRD_PARTY_BOTS.get(key)


def author_login(node: dict[str, Any]) -> str:
    """The login of a GraphQL node's author, or "" when the author is gone or malformed."""
    author = node.get("author")
    if not isinstance(author, dict):
        return ""
    login = author.get("login")
    return login if isinstance(login, str) else ""


def _oid(node: dict[str, Any], key: str) -> str | None:
    value = node.get(key)
    oid = value.get("oid") if isinstance(value, dict) else None
    return oid if isinstance(oid, str) else None


def opener_bot(thread: dict[str, Any]) -> str | None:
    """The third-party bot that opened a review thread, or None."""
    comments = thread.get("comments") or []
    return bot_name(author_login(comments[0])) if comments else None


def human_replies(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replies after the opener whose author is known and is not a third-party bot."""
    return [c for c in comments[1:] if author_login(c) and bot_name(author_login(c)) is None]


def extract_bot_threads(pull_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per review thread whose first comment came from a third-party bot."""
    rows: list[dict[str, Any]] = []
    for pr in pull_requests:
        for thread in pr.get("reviewThreads", []):
            comments = thread.get("comments") or []
            if not comments:
                continue
            opener = comments[0]
            bot = opener_bot(thread)
            if bot is None:
                continue
            replies = [
                {
                    "login": author_login(c),
                    "body": c.get("body") or "",
                    "created_at": c.get("createdAt"),
                }
                for c in human_replies(comments)
            ]
            rows.append(
                {
                    "pr": pr["number"],
                    "pr_title": pr.get("title", ""),
                    "pr_author": author_login(pr),
                    "pr_state": pr.get("state"),
                    "base_oid": pr.get("baseRefOid"),
                    "merge_oid": _oid(pr, "mergeCommit"),
                    "bot": bot,
                    "thread_id": thread.get("id"),
                    "path": thread.get("path"),
                    "line": thread.get("originalLine") or thread.get("line"),
                    "is_resolved": bool(thread.get("isResolved")),
                    "is_outdated": bool(thread.get("isOutdated")),
                    "commit": _oid(opener, "originalCommit") or _oid(opener, "commit"),
                    "created_at": opener.get("createdAt"),
                    "url": opener.get("url"),
                    "body": opener.get("body") or "",
                    "replies": replies,
                }
            )
    return rows
