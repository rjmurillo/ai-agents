#!/usr/bin/env python3
"""Get bot comments that need action based on lifecycle state analysis.

Implements a state machine to determine which comments truly need attention.
Analyzes eyes reactions, reply count, reply content, and thread resolution.

LIFECYCLE STATE MACHINE:
  State 1: NEW - 0 eyes AND 0 replies AND thread unresolved
  State 2: ACKNOWLEDGED - >0 eyes AND 0 replies AND thread unresolved
  State 3: IN_DISCUSSION - >0 eyes AND >0 replies AND thread unresolved
    Sub-states: WONT_FIX, FIX_DESCRIBED, FIX_COMMITTED, NEEDS_CLARIFICATION
  State 4: RESOLVED - Thread resolved

Exit codes follow ADR-035:
    0 - Success
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

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
    get_unresolved_review_threads,
    gh_api_paginated,
    resolve_repo_params,
)

# ---------------------------------------------------------------------------
# Lifecycle state detection
# ---------------------------------------------------------------------------

_WONTFIX_PATTERN = re.compile(
    r"won'?t\s*fix|wontfix|out\s+of\s+scope|follow-?up\s+pr|future\s+pr"
    r"|defer|deferred|tracked\s+in|separate\s+issue",
    re.IGNORECASE,
)
_COMMIT_HASH_PATTERN = re.compile(
    r"commit\s+[0-9a-fA-F]{7,40}|fixed\s+in\s+[0-9a-fA-F]{7,40}"
    r"|\b[0-9a-fA-F]{7,40}\b"
)
_CLARIFICATION_PATTERN = re.compile(
    r"\?\s*$|can\s+you\s+clarify|what\s+do\s+you\s+mean"
    r"|could\s+you\s+explain|not\s+sure\s+I\s+understand|need\s+more\s+context",
    re.IGNORECASE,
)
_FIX_DESCRIBED_PATTERN = re.compile(
    r"will\s+fix|fixing|updated|changed|modified|addressed"
    r"|implemented|added|removed",
    re.IGNORECASE,
)

# Domain classification
_SECURITY_PATTERN = re.compile(
    r"cwe-\d+|vulnerability|vulnerabilities|injection|xss|sql|csrf"
    r"|\bauth(?:entication|orization|enticat|orized)?\b"
    r"|secrets?|credentials?|toctou|symlink|traversal|sanitiz"
    r"|\bescap(?:e|ing)\b",
    re.IGNORECASE,
)
_BUG_PATTERN = re.compile(
    r"throws?\s+error|error\s+(?:occurs?|occurred|happens?|when|while)"
    r"|\bcrash(?:es|ed|ing)?\b|\bexception(?:s)?\b|\bfail(?:ed|s|ure|ing)\b"
    r"|null\s+(?:pointer|reference|ref)\b|undefined\s+(?:behavior|reference|variable)\b"
    r"|race\s+condition|deadlock|memory\s+leak",
    re.IGNORECASE,
)
_STYLE_PATTERN = re.compile(
    r"formatting|naming|indentation|whitespace|convention|code\s*style"
    r"|stylistic|readability|cleanup|refactor|refactoring",
    re.IGNORECASE,
)
_SUMMARY_PATTERN = re.compile(
    r"(?m)^\s*#{1,3}\s*(?:summary|overview|changes|walkthrough)",
    re.IGNORECASE,
)


def get_discussion_sub_state(reply_bodies: list[str]) -> str | None:
    """Analyze reply text to determine discussion sub-state."""
    if not reply_bodies:
        return None

    # Join last 3 replies for analysis
    combined = "\n".join(reply_bodies[-3:])

    if _WONTFIX_PATTERN.search(combined):
        return "WONT_FIX"
    if _COMMIT_HASH_PATTERN.search(combined):
        return "FIX_COMMITTED"
    if _CLARIFICATION_PATTERN.search(combined):
        return "NEEDS_CLARIFICATION"
    if _FIX_DESCRIBED_PATTERN.search(combined):
        return "FIX_DESCRIBED"

    return "NEEDS_CLARIFICATION"


def get_lifecycle_state(
    eyes_count: int, reply_count: int, is_thread_resolved: bool,
) -> str:
    """Determine the lifecycle state of a comment."""
    if is_thread_resolved:
        return "RESOLVED"
    if eyes_count == 0:
        return "NEW"
    if reply_count == 0:
        return "ACKNOWLEDGED"
    return "IN_DISCUSSION"


def comment_needs_action(lifecycle_state: str, sub_state: str | None) -> bool:
    """Determine if a comment needs action based on state."""
    if lifecycle_state == "RESOLVED":
        return False
    if lifecycle_state in ("NEW", "ACKNOWLEDGED"):
        return True
    if lifecycle_state == "IN_DISCUSSION":
        return sub_state not in ("WONT_FIX", "FIX_COMMITTED")
    return True


def classify_domain(body: str) -> str:
    """Classify a comment into a domain based on keyword matching."""
    if not body or not body.strip():
        return "general"
    if _SECURITY_PATTERN.search(body):
        return "security"
    if _BUG_PATTERN.search(body):
        return "bug"
    if _STYLE_PATTERN.search(body):
        return "style"
    if _SUMMARY_PATTERN.search(body):
        return "summary"
    return "general"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def get_unaddressed_comments(
    owner: str,
    repo: str,
    pr_number: int,
    bot_only: bool = True,
    only_unaddressed: bool = True,
) -> dict:
    """Get comments needing action, with lifecycle state analysis."""
    # Fetch all review comments
    try:
        raw_comments = gh_api_paginated(
            f"repos/{owner}/{repo}/pulls/{pr_number}/comments"
        )
    except SystemExit:
        raise
    except Exception as exc:
        print(
            f"Failed to fetch PR review comments for PR #{pr_number}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(3) from exc

    empty_result = {
        "Success": True,
        "PullRequest": pr_number,
        "Owner": owner,
        "Repo": repo,
        "TotalCount": 0,
        "LifecycleStateCounts": {"NEW": 0, "ACKNOWLEDGED": 0, "IN_DISCUSSION": 0, "RESOLVED": 0},
        "DiscussionSubStateCounts": {
            "WONT_FIX": 0, "FIX_DESCRIBED": 0,
            "FIX_COMMITTED": 0, "NEEDS_CLARIFICATION": 0,
        },
        "DomainCounts": {"security": 0, "bug": 0, "style": 0, "summary": 0, "general": 0},
        "AuthorSummary": [],
        "Comments": [],
    }

    if not raw_comments:
        print(f"PR #{pr_number}: 0 comments needing action", file=sys.stderr)
        return empty_result

    # Get unresolved thread comment IDs
    unresolved_threads = get_unresolved_review_threads(owner, repo, pr_number)
    unresolved_comment_ids: set[int] = set()
    for thread in unresolved_threads:
        nodes = thread.get("comments", {}).get("nodes", [])
        if nodes and nodes[0] and nodes[0].get("databaseId"):
            unresolved_comment_ids.add(nodes[0]["databaseId"])

    # Build reply lookup
    reply_bodies: dict[int, list[str]] = {}
    reply_counts: dict[int, int] = {}
    for comment in raw_comments:
        reply_to_id = comment.get("in_reply_to_id")
        if reply_to_id is not None:
            reply_bodies.setdefault(reply_to_id, []).append(comment.get("body", ""))
            reply_counts[reply_to_id] = reply_counts.get(reply_to_id, 0) + 1

    # Process root comments
    all_processed: list[dict] = []
    for comment in raw_comments:
        # Skip replies
        if comment.get("in_reply_to_id") is not None:
            continue

        # Apply bot filter
        if bot_only and comment.get("user", {}).get("type") != "Bot":
            continue

        cid = comment.get("id", 0)
        eyes_count = comment.get("reactions", {}).get("eyes", 0) or 0
        reply_count = reply_counts.get(cid, 0)
        is_resolved = cid not in unresolved_comment_ids

        state = get_lifecycle_state(eyes_count, reply_count, is_resolved)

        sub_state = None
        if state == "IN_DISCUSSION":
            sub_state = get_discussion_sub_state(reply_bodies.get(cid, []))

        needs_action = comment_needs_action(state, sub_state)

        all_processed.append({
            "Id": cid,
            "Author": comment.get("user", {}).get("login", ""),
            "AuthorType": comment.get("user", {}).get("type", ""),
            "Path": comment.get("path", ""),
            "Line": comment.get("line") or comment.get("original_line"),
            "Body": comment.get("body", ""),
            "Domain": classify_domain(comment.get("body", "")),
            "CreatedAt": comment.get("created_at", ""),
            "UpdatedAt": comment.get("updated_at", ""),
            "HtmlUrl": comment.get("html_url", ""),
            "InReplyToId": None,
            "IsReply": False,
            "LifecycleState": state,
            "DiscussionSubState": sub_state,
            "EyesCount": eyes_count,
            "ReplyCount": reply_count,
            "IsThreadResolved": is_resolved,
            "NeedsAction": needs_action,
        })

    # Apply filter
    if only_unaddressed:
        output_comments = [c for c in all_processed if c["NeedsAction"]]
    else:
        output_comments = all_processed

    # Calculate lifecycle state counts from ALL processed comments
    lifecycle_counts = {"NEW": 0, "ACKNOWLEDGED": 0, "IN_DISCUSSION": 0, "RESOLVED": 0}
    sub_state_counts = {
        "WONT_FIX": 0, "FIX_DESCRIBED": 0,
        "FIX_COMMITTED": 0, "NEEDS_CLARIFICATION": 0,
    }
    for c in all_processed:
        lifecycle_counts[c["LifecycleState"]] = lifecycle_counts.get(c["LifecycleState"], 0) + 1
        if c["LifecycleState"] == "IN_DISCUSSION" and c["DiscussionSubState"]:
            key = c["DiscussionSubState"]
            sub_state_counts[key] = sub_state_counts.get(key, 0) + 1

    # Domain counts from output
    domain_counts = {"security": 0, "bug": 0, "style": 0, "summary": 0, "general": 0}
    for c in output_comments:
        domain = c.get("Domain", "general")
        domain_counts[domain] = domain_counts.get(domain, 0) + 1

    # Author summary
    author_counter: Counter[str] = Counter()
    for c in output_comments:
        if c.get("Author"):
            author_counter[c["Author"]] += 1
    author_summary = [
        {"Author": author, "Count": count}
        for author, count in author_counter.items()
    ]

    actionable_count = sum(1 for c in all_processed if c["NeedsAction"])

    # Console summary
    state_parts = []
    for state_name in ("NEW", "ACKNOWLEDGED", "IN_DISCUSSION"):
        if lifecycle_counts[state_name] > 0:
            state_parts.append(f"{state_name}({lifecycle_counts[state_name]})")
    state_summary = f" | {', '.join(state_parts)}" if state_parts else ""
    print(
        f"PR #{pr_number}: {actionable_count} comments needing action{state_summary}",
        file=sys.stderr,
    )

    return {
        "Success": True,
        "PullRequest": pr_number,
        "Owner": owner,
        "Repo": repo,
        "TotalCount": len(output_comments),
        "LifecycleStateCounts": lifecycle_counts,
        "DiscussionSubStateCounts": sub_state_counts,
        "DomainCounts": domain_counts,
        "AuthorSummary": author_summary,
        "Comments": output_comments,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get bot comments that need action based on lifecycle state analysis.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True,
        help="PR number",
    )
    parser.add_argument(
        "--bot-only", action="store_true", default=True,
        help="Only return bot comments (default: true)",
    )
    parser.add_argument(
        "--no-bot-only", action="store_false", dest="bot_only",
        help="Include all comments regardless of author type",
    )
    parser.add_argument(
        "--only-unaddressed", action="store_true", default=True,
        help="Only return comments needing action (default: true)",
    )
    parser.add_argument(
        "--no-only-unaddressed", action="store_false", dest="only_unaddressed",
        help="Include all comments with full lifecycle state info",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved.owner
    repo = resolved.repo

    result = get_unaddressed_comments(
        owner,
        repo,
        args.pull_request,
        bot_only=args.bot_only,
        only_unaddressed=args.only_unaddressed,
    )

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
