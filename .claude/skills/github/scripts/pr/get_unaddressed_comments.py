#!/usr/bin/env python3
"""Get bot comments that need action based on lifecycle state analysis.

Implements a state machine for comment lifecycle:
  NEW -> ACKNOWLEDGED (eyes reaction) -> IN_DISCUSSION -> RESOLVED

Exit codes (ADR-035):
    0 = Success
    3 = API error
    4 = Not authenticated
"""

import argparse
import json
import os
import re
import sys

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    gh_api_paginated,
    gh_graphql,
    resolve_repo_params,
    write_error_and_exit,
)


def get_discussion_sub_state(reply_bodies: list[str]) -> str | None:
    """Analyze reply text to determine discussion sub-state."""
    if not reply_bodies:
        return None

    combined = "\n".join(reply_bodies[-3:]).lower()

    wontfix_pat = (
        r"won'?t\s*fix|wontfix|out\s+of\s+scope"
        r"|follow-?up\s+pr|future\s+pr|defer"
        r"|tracked\s+in|separate\s+issue"
    )
    if re.search(wontfix_pat, combined):
        return "WONT_FIX"
    commit_pat = (
        r"commit\s+[0-9a-fA-F]{7,40}"
        r"|fixed\s+in\s+[0-9a-fA-F]{7,40}"
        r"|\b[0-9a-fA-F]{7,40}\b"
    )
    recent = "\n".join(reply_bodies[-3:])
    if re.search(commit_pat, recent):
        return "FIX_COMMITTED"
    clarify_pat = (
        r"\?\s*$|can\s+you\s+clarify"
        r"|what\s+do\s+you\s+mean"
        r"|could\s+you\s+explain"
    )
    if re.search(clarify_pat, combined):
        return "NEEDS_CLARIFICATION"
    fix_pat = (
        r"will\s+fix|fixing|updated|changed"
        r"|modified|addressed|implemented"
        r"|added|removed"
    )
    if re.search(fix_pat, combined):
        return "FIX_DESCRIBED"

    return "NEEDS_CLARIFICATION"


def get_lifecycle_state(eyes_count: int, reply_count: int, is_resolved: bool) -> str:
    """Determine comment lifecycle state."""
    if is_resolved:
        return "RESOLVED"
    if eyes_count == 0:
        return "NEW"
    if reply_count == 0:
        return "ACKNOWLEDGED"
    return "IN_DISCUSSION"


def needs_action(state: str, sub_state: str | None) -> bool:
    """Determine if a comment needs action based on state."""
    if state == "RESOLVED":
        return False
    if state in ("NEW", "ACKNOWLEDGED"):
        return True
    if state == "IN_DISCUSSION":
        return sub_state not in ("WONT_FIX", "FIX_COMMITTED")
    return True


def classify_domain(body: str) -> str:
    """Classify a comment into a domain based on keywords."""
    if not body:
        return "general"
    lower = body.lower()

    security_pat = (
        r"cwe-\d+|vulnerability|injection|xss|csrf"
        r"|auth|secrets?|credentials?|traversal|sanitiz"
    )
    if re.search(security_pat, lower):
        return "security"
    bug_pat = (
        r"throws?\s+error|crash|exception|fail"
        r"|null\s+(?:pointer|reference)"
        r"|race\s+condition|deadlock"
    )
    if re.search(bug_pat, lower):
        return "bug"
    style_pat = (
        r"formatting|naming|indentation|whitespace"
        r"|convention|code\s*style|readability|refactor"
    )
    if re.search(style_pat, lower):
        return "style"
    if re.search(r"(?m)^\s*#{1,3}\s*(?:summary|overview|changes|walkthrough)", lower):
        return "summary"
    return "general"


UNRESOLVED_QUERY = """
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes { databaseId }
          }
        }
      }
    }
  }
}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Get unaddressed PR comments")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    parser.add_argument("--bot-only", action="store_true", default=True, help="Only bot comments")
    parser.add_argument("--no-bot-only", dest="bot_only", action="store_false")
    parser.add_argument(
        "--only-unaddressed", action="store_true",
        default=True, help="Only unaddressed",
    )
    parser.add_argument(
        "--no-only-unaddressed",
        dest="only_unaddressed", action="store_false",
    )
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["owner"], resolved["repo"]

    try:
        raw_comments = gh_api_paginated(f"repos/{owner}/{repo}/pulls/{args.pull_request}/comments")
    except Exception as e:
        write_error_and_exit(f"Failed to fetch PR review comments: {e}", 3)

    if not raw_comments:
        output = {
            "Success": True, "PullRequest": args.pull_request,
            "Owner": owner, "Repo": repo, "TotalCount": 0,
            "LifecycleStateCounts": {
                "NEW": 0, "ACKNOWLEDGED": 0,
                "IN_DISCUSSION": 0, "RESOLVED": 0,
            },
            "DiscussionSubStateCounts": {
                "WONT_FIX": 0, "FIX_DESCRIBED": 0,
                "FIX_COMMITTED": 0,
                "NEEDS_CLARIFICATION": 0,
            },
            "DomainCounts": {
                "security": 0, "bug": 0, "style": 0,
                "summary": 0, "general": 0,
            },
            "AuthorSummary": [], "Comments": [],
        }
        print(json.dumps(output, indent=2))
        print(f"PR #{args.pull_request}: 0 comments needing action", file=sys.stderr)
        return

    # Get unresolved thread IDs
    try:
        thread_data = gh_graphql(UNRESOLVED_QUERY, {
            "owner": owner, "repo": repo, "prNumber": args.pull_request,
        })
        pr_data = thread_data.get("repository", {}).get("pullRequest", {})
        threads = pr_data.get("reviewThreads", {}).get("nodes", [])
        unresolved_ids = set()
        for t in threads:
            if not t.get("isResolved", False):
                comments = t.get("comments", {}).get("nodes", [])
                if comments and comments[0].get("databaseId"):
                    unresolved_ids.add(comments[0]["databaseId"])
    except Exception:
        unresolved_ids = set()

    # Build reply lookup
    reply_bodies: dict[int, list[str]] = {}
    reply_counts: dict[int, int] = {}
    for c in raw_comments:
        reply_to = c.get("in_reply_to_id")
        if reply_to:
            reply_bodies.setdefault(reply_to, []).append(c.get("body", ""))
            reply_counts[reply_to] = reply_counts.get(reply_to, 0) + 1

    # Process root comments only
    all_processed = []
    for c in raw_comments:
        if c.get("in_reply_to_id"):
            continue
        if args.bot_only and c.get("user", {}).get("type") != "Bot":
            continue

        cid = c["id"]
        eyes = c.get("reactions", {}).get("eyes", 0)
        rcount = reply_counts.get(cid, 0)
        is_resolved = cid not in unresolved_ids

        state = get_lifecycle_state(eyes, rcount, is_resolved)
        sub_state = (
            get_discussion_sub_state(reply_bodies.get(cid, []))
            if state == "IN_DISCUSSION"
            else None
        )

        all_processed.append({
            "Id": cid,
            "Author": c.get("user", {}).get("login"),
            "AuthorType": c.get("user", {}).get("type"),
            "Path": c.get("path"),
            "Line": c.get("line") or c.get("original_line"),
            "Body": c.get("body"),
            "Domain": classify_domain(c.get("body", "")),
            "CreatedAt": c.get("created_at"),
            "HtmlUrl": c.get("html_url"),
            "LifecycleState": state,
            "DiscussionSubState": sub_state,
            "EyesCount": eyes,
            "ReplyCount": rcount,
            "IsThreadResolved": is_resolved,
            "NeedsAction": needs_action(state, sub_state),
        })

    if args.only_unaddressed:
        filtered = [c for c in all_processed if c["NeedsAction"]]
    else:
        filtered = all_processed

    # Counts
    lc = {"NEW": 0, "ACKNOWLEDGED": 0, "IN_DISCUSSION": 0, "RESOLVED": 0}
    dc = {"WONT_FIX": 0, "FIX_DESCRIBED": 0, "FIX_COMMITTED": 0, "NEEDS_CLARIFICATION": 0}
    for c in all_processed:
        lc[c["LifecycleState"]] = lc.get(c["LifecycleState"], 0) + 1
        if c["LifecycleState"] == "IN_DISCUSSION" and c["DiscussionSubState"]:
            dc[c["DiscussionSubState"]] = dc.get(c["DiscussionSubState"], 0) + 1

    domain_counts = {"security": 0, "bug": 0, "style": 0, "summary": 0, "general": 0}
    for c in filtered:
        domain_counts[c["Domain"]] = domain_counts.get(c["Domain"], 0) + 1

    author_counts: dict[str, int] = {}
    for c in filtered:
        author = c.get("Author", "unknown")
        author_counts[author] = author_counts.get(author, 0) + 1

    output = {
        "Success": True, "PullRequest": args.pull_request,
        "Owner": owner, "Repo": repo,
        "TotalCount": len(filtered),
        "LifecycleStateCounts": lc,
        "DiscussionSubStateCounts": dc,
        "DomainCounts": domain_counts,
        "AuthorSummary": [{"Author": a, "Count": n} for a, n in author_counts.items()],
        "Comments": filtered,
    }

    print(json.dumps(output, indent=2))
    actionable = sum(1 for c in all_processed if c["NeedsAction"])
    print(f"PR #{args.pull_request}: {actionable} comments needing action", file=sys.stderr)


if __name__ == "__main__":
    main()
