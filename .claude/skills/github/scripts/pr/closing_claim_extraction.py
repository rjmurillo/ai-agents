"""Pure claim-extraction and classification helpers for audit_closing_claims.py.

Split out of the main script (which orchestrates GraphQL/REST fetching, CLI
parsing, and output) purely to keep that file under the repository's
500-line taste-lint ceiling (`.claude/rules/code-quality.md`). Nothing here
performs I/O: no `subprocess`, no `gh_graphql`. Every function is a plain
text transform, which is also why `audit_closing_claims.py`'s tests patch
this module's callers (`fetch_open_prs`, `fetch_repo_squash_setting`) rather
than anything defined here.

Body claims (`extract_claims`, `classify_claim`) are Markdown-aware: they
neutralise fenced code, code spans, and HTML comments before matching, since
GitHub renders a PR body as Markdown before scanning it for closing
keywords. Commit-message and auto-merge-override claims
(`extract_reachable_claims`, `classify_commit_claim`) are plain-text: GitHub
does not render commit messages or merge-commit overrides as Markdown, so
only the escaped-hash class applies there (see `audit_closing_claims.py`'s
module docstring for the full reachability contract this module implements).
"""

from __future__ import annotations

import re
from typing import Any

# Repository squash_merge_commit_message values that fold commit messages
# into the eventual squash commit text. Source: GitHub REST
# `repos/{owner}/{repo}` field `squash_merge_commit_message`, confirmed live
# during Issue #4462 triage (values PR_BODY, COMMIT_MESSAGES,
# PR_BODY_AND_COMMIT_DETAILS, BLANK).
COMMIT_REACHING_SQUASH_SETTINGS = frozenset({"COMMIT_MESSAGES", "PR_BODY_AND_COMMIT_DETAILS"})

# GitHub's recognised closing keywords (case-insensitive).
CLOSING_KEYWORDS_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)(?::)?\s+"
    r"(?:(?P<owner>[a-zA-Z0-9_.-]+)/(?P<repo2>[a-zA-Z0-9_.-]+))?(?P<escape>\\?)#(?P<number>\d+)",
    re.IGNORECASE,
)


def _strip_fenced_code(text: str) -> tuple[str, set[int]]:
    """Return (text_with_fenced_replaced, set_of_positions_in_fenced_blocks).

    Replaces fenced code block content with spaces to neutralise keyword
    matches within them. Returns the original text positions that are inside
    fenced code.
    """
    fenced_positions: set[int] = set()
    result = list(text)
    in_fence = False
    fence_char = ""
    opening_fence_length = 0
    i = 0
    while i < len(text):
        if not in_fence:
            is_line_start = i == 0 or text[i - 1] == "\n"
            m = re.match(r" {0,3}(`{3,}|~{3,})", text[i:]) if is_line_start else None
            if m:
                fence = m.group(1)
                fence_char = fence[0]
                opening_fence_length = len(fence)
                in_fence = True
                # Mark the fence opener
                for j in range(i, min(i + len(m.group(0)), len(text))):
                    fenced_positions.add(j)
                i += len(m.group(0))
                # Skip rest of the opening line
                while i < len(text) and text[i] != "\n":
                    fenced_positions.add(i)
                    i += 1
            else:
                i += 1
        else:
            # Look for closing fence
            is_line_start = i == 0 or text[i - 1] == "\n"
            m = (
                re.match(
                    rf" {{0,3}}{re.escape(fence_char)}"
                    rf"{{{opening_fence_length},}}(?=[ \t]*(?:\n|\Z))",
                    text[i:],
                )
                if is_line_start
                else None
            )
            if m:
                for j in range(i, min(i + len(m.group(0)), len(text))):
                    fenced_positions.add(j)
                i += len(m.group(0))
                in_fence = False
            else:
                fenced_positions.add(i)
                i += 1
    # Replace fenced positions with space in result
    for pos in fenced_positions:
        result[pos] = " "
    return "".join(result), fenced_positions


def _strip_html_comments(text: str) -> tuple[str, set[int]]:
    """Return (text_with_html_comments_replaced, set_of_comment_positions)."""
    comment_positions: set[int] = set()
    result = list(text)
    for m in re.finditer(r"<!--.*?(?:-->|\Z)", text, re.DOTALL):
        for i in range(m.start(), m.end()):
            comment_positions.add(i)
            result[i] = " "
    return "".join(result), comment_positions


def _is_escaped_hash(text: str, match: re.Match[str]) -> bool:
    """Return whether the matched hash is preceded by a backslash escape."""
    hash_pos = match.start() + match.group(0).index("#")
    return hash_pos > 0 and text[hash_pos - 1] == "\\"


def classify_claim(
    text: str,
    match: re.Match[str],
    fenced_positions: set[int],
    html_comment_positions: set[int],
) -> str:
    """Return the Markdown context classification for a body keyword match."""
    start = match.start()

    if start in fenced_positions:
        return "fenced_code"

    if start in html_comment_positions:
        return "html_comment"

    if _is_escaped_hash(text, match):
        return "escaped_hash"

    if _inside_code_span(text, start):
        return "code_span"

    return "active"


def classify_commit_claim(text: str, match: re.Match[str]) -> str:
    """Return the plain-text classification for a commit/override keyword match.

    Commit messages and auto-merge commit-message overrides are not
    rendered as Markdown by GitHub, so only the escaped-hash and active
    classes apply; code_span, fenced_code, and html_comment are body-only
    concepts (see this module's docstring).
    """
    if _is_escaped_hash(text, match):
        return "escaped_hash"
    return "active"


def _inside_code_span(text: str, position: int) -> bool:
    """Return whether position is inside a paired backtick code span."""
    openers: dict[int, re.Match[str]] = {}
    for run in re.finditer(r"`+", text):
        delimiter_length = len(run.group(0))
        opener = openers.pop(delimiter_length, None)
        if opener is None:
            openers[delimiter_length] = run
            continue
        if opener.end() <= position < run.start():
            return True
    return False


def resolve_closing_refs(
    pr_closing_nodes: list[dict[str, Any]],
) -> dict[tuple[str, str, int], str]:
    """Build an owner, repository, and issue state map from closing references."""
    result: dict[tuple[str, str, int], str] = {}
    for node in pr_closing_nodes:
        num = node.get("number")
        state = node.get("state", "")
        name_with_owner = (node.get("repository") or {}).get("nameWithOwner", "")
        if num is not None and "/" in name_with_owner:
            target_owner, target_repo = name_with_owner.split("/", 1)
            result[(target_owner.casefold(), target_repo.casefold(), int(num))] = state
    return result


def extract_claims(
    pr_number: int,
    body: str,
    base_branch: str,
    closing_refs: dict[tuple[str, str, int], str],
    owner: str,
    repo: str,
    default_branch: str = "main",
) -> list[dict[str, Any]]:
    """Parse closing claims from one PR body."""
    if not body:
        return []

    _, fenced_positions = _strip_fenced_code(body)
    _, html_positions = _strip_html_comments(body)

    claims: list[dict[str, Any]] = []
    for m in CLOSING_KEYWORDS_RE.finditer(body):
        target_num = int(m.group("number"))
        context_cls = classify_claim(body, m, fenced_positions, html_positions)
        target_owner = m.group("owner") or owner
        target_repo_name = m.group("repo2") or repo
        target_key = (
            target_owner.casefold(),
            target_repo_name.casefold(),
            target_num,
        )

        target_state = closing_refs.get(target_key, "unknown")
        will_close = (
            context_cls == "active"
            and base_branch == default_branch
            and target_key in closing_refs
        )

        claims.append({
            "pr_number": pr_number,
            "claim_text": m.group(0),
            "target_number": target_num,
            "target_owner": target_owner,
            "target_repo": target_repo_name,
            "target_state": target_state,
            "base_branch": base_branch,
            "context_class": context_cls,
            "github_will_close": will_close,
            "source": "body",
            "reaches_squash": will_close,
            "unsupported": False,
        })
    return claims


def extract_reachable_claims(
    pr_number: int,
    text: str,
    source: str,
    reaches_squash: bool,
    closing_refs: dict[tuple[str, str, int], str],
    owner: str,
    repo: str,
) -> list[dict[str, Any]]:
    """Parse closing claims from commit-message or auto-merge-override text.

    Unlike `extract_claims`, this treats the input as plain text: no fenced
    code, code-span, or HTML-comment neutralisation, because GitHub does not
    render commit messages or merge-commit overrides as Markdown. Whether a
    claim can actually close its target on merge is `reaches_squash`,
    supplied by the caller from the repository's squash-message setting and
    any per-PR auto-merge override (see `audit_closing_claims.py`'s module
    docstring). `unsupported` is computed later once every source's claims
    for a PR are collected, so it always starts `False` here.
    """
    if not text:
        return []

    claims: list[dict[str, Any]] = []
    for m in CLOSING_KEYWORDS_RE.finditer(text):
        target_num = int(m.group("number"))
        context_cls = classify_commit_claim(text, m)
        target_owner = m.group("owner") or owner
        target_repo_name = m.group("repo2") or repo
        target_key = (target_owner.casefold(), target_repo_name.casefold(), target_num)
        target_state = closing_refs.get(target_key, "unknown")

        claims.append({
            "pr_number": pr_number,
            "claim_text": m.group(0),
            "target_number": target_num,
            "target_owner": target_owner,
            "target_repo": target_repo_name,
            "target_state": target_state,
            "context_class": context_cls,
            "github_will_close": False,
            "source": source,
            "reaches_squash": reaches_squash and context_cls == "active",
            "unsupported": False,
        })
    return claims


def mark_unsupported_claims(claims: list[dict[str, Any]]) -> bool:
    """Flag non-body claims that reach the squash commit unsupported by the body.

    A commit or auto-merge claim is unsupported when no active body claim
    for the same target already has `github_will_close: True`. Mutates the
    claims in place and returns whether any unsupported claim was found.
    """
    supported_targets = {
        (c["target_owner"].casefold(), c["target_repo"].casefold(), c["target_number"])
        for c in claims
        if c["source"] == "body" and c["github_will_close"]
    }

    found = False
    for claim in claims:
        if claim["source"] == "body" or not claim["reaches_squash"]:
            continue
        target_key = (
            claim["target_owner"].casefold(),
            claim["target_repo"].casefold(),
            claim["target_number"],
        )
        if target_key not in supported_targets:
            claim["unsupported"] = True
            found = True
    return found
