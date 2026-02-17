#!/usr/bin/env python3
"""Get all comments for a GitHub Pull Request with domain classification and stale detection.

Retrieves PR review comments (code-level) and optionally issue comments (PR-level)
with full pagination support. Each comment is classified into a domain (security,
bug, style, summary, or general) for priority-based triage.

Can also detect stale comments that reference deleted files, out-of-range lines,
or changed code.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters
    2 - Not found
    3 - API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.parse
from collections import Counter
from typing import Any

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
    get_unresolved_review_threads,
    gh_api_paginated,
    resolve_repo_params,
)

# ---------------------------------------------------------------------------
# Domain classification
# ---------------------------------------------------------------------------

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
# Stale detection helpers
# ---------------------------------------------------------------------------


def get_pr_head_sha(owner: str, repo: str, pr_number: int) -> str | None:
    """Fetch the PR's head commit SHA."""
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/pulls/{pr_number}",
            "--jq", ".head.sha",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(
            f"WARNING: Failed to fetch PR head SHA. Error: {result.stderr}",
            file=sys.stderr,
        )
        return None
    return result.stdout.strip() or None


def get_pr_file_tree(owner: str, repo: str, head_sha: str | None) -> list[str]:
    """Fetch and return file paths in the PR's head commit."""
    if not head_sha:
        return []

    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/git/trees/{head_sha}?recursive=1",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(
            f"WARNING: Failed to fetch file tree. Error: {result.stderr}",
            file=sys.stderr,
        )
        return []

    try:
        tree_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    if not tree_data or not tree_data.get("tree"):
        return []

    return [
        item["path"]
        for item in tree_data["tree"]
        if item.get("type") == "blob"
    ]


def get_file_content(
    owner: str,
    repo: str,
    path: str,
    head_sha: str | None,
    content_cache: dict[str, str | None],
) -> str | None:
    """Fetch and cache file content from PR's head commit."""
    if path in content_cache:
        return content_cache[path]

    if not head_sha:
        content_cache[path] = None
        return None

    encoded_path = urllib.parse.quote(path, safe="")
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/contents/{encoded_path}?ref={head_sha}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        content_cache[path] = None
        return None

    try:
        content_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        content_cache[path] = None
        return None

    if not content_data or not content_data.get("content"):
        content_cache[path] = None
        return None

    try:
        decoded = base64.b64decode(content_data["content"]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        content_cache[path] = None
        return None

    content_cache[path] = decoded
    return decoded


def test_line_exists(line: int, content: str) -> bool:
    """Check if a line number exists in the file content."""
    if not content:
        return False
    line_count = len(re.split(r"\r\n|\r|\n", content))
    return 0 < line <= line_count


def test_diff_hunk_match(line: int, diff_hunk: str, content: str) -> bool:
    """Check if diff hunk context still matches current file content."""
    if not diff_hunk or not content:
        return True

    # Extract code lines from diff hunk
    diff_lines = []
    for dl in diff_hunk.splitlines():
        if dl.startswith(" ") or (dl.startswith("+") and not dl.startswith("++")):
            diff_lines.append(dl[1:] if dl else "")

    if not diff_lines:
        return True

    content_lines = re.split(r"\r\n|\r|\n", content)
    if not content_lines:
        return False

    zero_based = line - 1
    start = max(0, zero_based - 3)
    end = min(len(content_lines) - 1, zero_based + 3)

    if start >= len(content_lines) or end < 0 or start > end:
        return False

    context_lines = content_lines[start : end + 1]

    # Fuzzy match: at least 50% of non-empty diff lines found in context
    match_count = 0
    non_empty = [dl for dl in diff_lines if dl.strip()]
    if not non_empty:
        return True

    for dl in non_empty:
        trimmed = dl.strip()
        for cl in context_lines:
            if cl.strip() == trimmed:
                match_count += 1
                break

    return (match_count / len(non_empty)) >= 0.5


def get_staleness(
    comment: dict,
    owner: str,
    repo: str,
    file_tree: list[str],
    content_cache: dict[str, str | None],
    head_sha: str | None,
) -> dict:
    """Determine if a comment is stale."""
    comment_type = comment.get("CommentType", "")
    path = comment.get("Path")

    if comment_type == "Issue" or not path:
        return {"Stale": False, "StaleReason": None}

    if path not in file_tree:
        return {"Stale": True, "StaleReason": "FileDeleted"}

    file_content = get_file_content(owner, repo, path, head_sha, content_cache)
    if file_content is None:
        return {"Stale": False, "StaleReason": None}

    line = comment.get("Line")
    if line and not test_line_exists(line, file_content):
        return {"Stale": True, "StaleReason": "LineOutOfRange"}

    diff_hunk = comment.get("DiffHunk")
    if diff_hunk and line:
        if not test_diff_hunk_match(line, diff_hunk, file_content):
            return {"Stale": True, "StaleReason": "CodeChanged"}

    return {"Stale": False, "StaleReason": None}


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def get_pr_review_comments(
    owner: str,
    repo: str,
    pr_number: int,
    author: str = "",
    include_diff_hunk: bool = False,
    include_issue_comments: bool = False,
    detect_stale: bool = False,
    exclude_stale: bool = False,
    only_stale: bool = False,
    group_by_domain: bool = False,
    only_unaddressed: bool = False,
    bot_only: bool = False,
) -> dict:
    """Get all comments for a PR with optional filtering and classification."""
    # Initialize stale detection caches
    file_tree: list[str] = []
    content_cache: dict[str, str | None] = {}
    head_sha: str | None = None

    if detect_stale:
        head_sha = get_pr_head_sha(owner, repo, pr_number)
        file_tree = get_pr_file_tree(owner, repo, head_sha)
        if not file_tree:
            print(
                "WARNING: File tree is empty. Stale detection disabled.",
                file=sys.stderr,
            )

    # Fetch review comments
    try:
        review_comments = gh_api_paginated(
            f"repos/{owner}/{repo}/pulls/{pr_number}/comments"
        )
    except SystemExit:
        raise
    except Exception as exc:
        error_and_exit(
            f"Failed to fetch PR review comments for PR #{pr_number}: {exc}",
            3,
        )

    processed_review: list[dict] = []
    for comment in review_comments:
        login = comment.get("user", {}).get("login", "")
        if author and login != author:
            continue

        line = comment.get("line") or comment.get("original_line")
        diff_hunk = comment.get("diff_hunk", "")

        stale_info: dict = {"Stale": None, "StaleReason": None}
        if detect_stale:
            stale_info = get_staleness(
                {
                    "CommentType": "Review",
                    "Path": comment.get("path"),
                    "Line": line,
                    "DiffHunk": diff_hunk,
                },
                owner, repo, file_tree, content_cache, head_sha,
            )

        processed_review.append({
            "Id": comment.get("id"),
            "CommentType": "Review",
            "Author": login,
            "AuthorType": comment.get("user", {}).get("type", ""),
            "Path": comment.get("path"),
            "Line": line,
            "Side": comment.get("side"),
            "Body": comment.get("body", ""),
            "Domain": classify_domain(comment.get("body", "")),
            "CreatedAt": comment.get("created_at"),
            "UpdatedAt": comment.get("updated_at"),
            "InReplyToId": comment.get("in_reply_to_id"),
            "IsReply": comment.get("in_reply_to_id") is not None,
            "DiffHunk": diff_hunk if include_diff_hunk else None,
            "HtmlUrl": comment.get("html_url"),
            "CommitId": comment.get("commit_id"),
            "Stale": stale_info["Stale"],
            "StaleReason": stale_info["StaleReason"],
            "EyesCount": comment.get("reactions", {}).get("eyes", 0) or 0,
        })

    # Fetch issue comments if requested
    processed_issue: list[dict] = []
    if include_issue_comments:
        try:
            issue_comments = gh_api_paginated(
                f"repos/{owner}/{repo}/issues/{pr_number}/comments"
            )
        except SystemExit:
            raise
        except Exception as exc:
            error_and_exit(
                f"Failed to fetch issue comments for PR #{pr_number}: {exc}",
                3,
            )

        for comment in issue_comments:
            login = comment.get("user", {}).get("login", "")
            if author and login != author:
                continue

            processed_issue.append({
                "Id": comment.get("id"),
                "CommentType": "Issue",
                "Author": login,
                "AuthorType": comment.get("user", {}).get("type", ""),
                "Path": None,
                "Line": None,
                "Side": None,
                "Body": comment.get("body", ""),
                "Domain": classify_domain(comment.get("body", "")),
                "CreatedAt": comment.get("created_at"),
                "UpdatedAt": comment.get("updated_at"),
                "InReplyToId": None,
                "IsReply": False,
                "DiffHunk": None,
                "HtmlUrl": comment.get("html_url"),
                "CommitId": None,
                "Stale": False if detect_stale else None,
                "StaleReason": None,
                "EyesCount": comment.get("reactions", {}).get("eyes", 0) or 0,
            })

    # Combine
    all_comments = processed_review + processed_issue

    # Apply stale filters
    if detect_stale:
        if exclude_stale:
            all_comments = [c for c in all_comments if not c.get("Stale")]
        elif only_stale:
            all_comments = [c for c in all_comments if c.get("Stale") is True]

    # Apply unaddressed filtering
    if only_unaddressed:
        unresolved_threads = get_unresolved_review_threads(owner, repo, pr_number)
        unresolved_ids: set[int] = set()
        for thread in unresolved_threads:
            nodes = thread.get("comments", {}).get("nodes", [])
            if nodes and nodes[0] and nodes[0].get("databaseId"):
                unresolved_ids.add(nodes[0]["databaseId"])

        filtered: list[dict] = []
        for c in all_comments:
            if bot_only and c.get("AuthorType") != "Bot":
                continue
            is_unacknowledged = c.get("EyesCount", 0) == 0
            is_unresolved = c.get("Id") in unresolved_ids
            if is_unacknowledged or is_unresolved:
                lifecycle = "NEW" if c.get("EyesCount", 0) == 0 else "ACKNOWLEDGED"
                c["LifecycleState"] = lifecycle
                filtered.append(c)

        all_comments = filtered

    # Sort by creation date
    all_comments.sort(key=lambda c: c.get("CreatedAt") or "")

    # Calculate counts
    stale_count = sum(1 for c in all_comments if c.get("Stale") is True) if detect_stale else 0
    review_count = sum(1 for c in all_comments if c.get("CommentType") == "Review")
    issue_count = sum(1 for c in all_comments if c.get("CommentType") == "Issue")

    domain_counter: Counter[str] = Counter()
    for c in all_comments:
        domain_counter[c.get("Domain", "general")] += 1
    domain_counts = {
        "security": domain_counter.get("security", 0),
        "bug": domain_counter.get("bug", 0),
        "style": domain_counter.get("style", 0),
        "summary": domain_counter.get("summary", 0),
        "general": domain_counter.get("general", 0),
    }

    author_counter: Counter[str] = Counter()
    for c in all_comments:
        if c.get("Author"):
            author_counter[c["Author"]] += 1
    author_summary = [
        {"Author": a, "Count": cnt} for a, cnt in author_counter.items()
    ]

    # Handle GroupByDomain output mode
    if group_by_domain:
        grouped: dict[str, Any] = {
            "Security": [], "Bug": [], "Style": [], "Summary": [], "General": [],
        }
        for c in all_comments:
            domain = c.get("Domain", "general")
            cap = domain.capitalize()
            if cap in grouped:
                grouped[cap].append(c)

        cap_domain_counts = {k.capitalize(): v for k, v in domain_counts.items()}

        grouped["TotalComments"] = len(all_comments)
        grouped["DomainCounts"] = cap_domain_counts
        grouped["StaleCount"] = stale_count

        # Console summary
        domains = ("Security", "Bug", "Style", "Summary", "General")
        parts = [
            f"{d}({cap_domain_counts.get(d, 0)})" for d in domains
        ]
        print(
            f"PR #{pr_number}: Grouped by domain: {', '.join(parts)}",
            file=sys.stderr,
        )

        return grouped

    # Standard output mode
    top_level_count = sum(1 for c in all_comments if not c.get("IsReply"))
    reply_count = sum(1 for c in all_comments if c.get("IsReply"))

    output = {
        "Success": True,
        "PullRequest": pr_number,
        "Owner": owner,
        "Repo": repo,
        "TotalComments": len(all_comments),
        "ReviewCommentCount": review_count,
        "IssueCommentCount": issue_count,
        "TopLevelCount": top_level_count,
        "ReplyCount": reply_count,
        "StaleCount": stale_count,
        "DomainCounts": domain_counts,
        "AuthorSummary": author_summary,
        "Comments": all_comments,
    }

    # Console summary
    review_text = "review comment" if review_count == 1 else "review comments"
    summary = f"PR #{pr_number}: {review_count} {review_text}"
    if include_issue_comments:
        issue_text = "issue comment" if issue_count == 1 else "issue comments"
        summary += f" + {issue_count} {issue_text}"
    if detect_stale and stale_count > 0:
        stale_text = "stale comment" if stale_count == 1 else "stale comments"
        summary += f" ({stale_count} {stale_text})"

    domain_parts = []
    for d in ("security", "bug", "style", "summary", "general"):
        cnt = domain_counts.get(d, 0)
        if cnt > 0:
            domain_parts.append(f"{d.capitalize()}({cnt})")
    if domain_parts:
        summary += f" | Domains: {', '.join(domain_parts)}"

    print(summary, file=sys.stderr)

    return output


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get all comments for a GitHub PR with domain classification.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True,
        help="PR number",
    )
    parser.add_argument(
        "--author", default="",
        help="Filter by author login name",
    )
    parser.add_argument(
        "--include-diff-hunk", action="store_true",
        help="Include diff context for each review comment",
    )
    parser.add_argument(
        "--include-issue-comments", action="store_true",
        help="Also fetch issue comments (top-level PR comments)",
    )
    parser.add_argument(
        "--detect-stale", action="store_true",
        help="Analyze comments for staleness (deleted files, changed code)",
    )
    parser.add_argument(
        "--exclude-stale", action="store_true",
        help="Filter out stale comments (requires --detect-stale)",
    )
    parser.add_argument(
        "--only-stale", action="store_true",
        help="Return only stale comments (requires --detect-stale)",
    )
    parser.add_argument(
        "--group-by-domain", action="store_true",
        help="Group comments by domain instead of flat array",
    )
    parser.add_argument(
        "--only-unaddressed", action="store_true",
        help="Filter to comments needing attention",
    )
    parser.add_argument(
        "--bot-only", action="store_true",
        help="With --only-unaddressed, filter to bot comments only",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Validate parameter combinations
    if args.exclude_stale and not args.detect_stale:
        print(
            "--exclude-stale requires --detect-stale",
            file=sys.stderr,
        )
        return 1
    if args.only_stale and not args.detect_stale:
        print(
            "--only-stale requires --detect-stale",
            file=sys.stderr,
        )
        return 1
    if args.exclude_stale and args.only_stale:
        print(
            "--exclude-stale and --only-stale are mutually exclusive",
            file=sys.stderr,
        )
        return 1
    if args.bot_only and not args.only_unaddressed:
        print(
            "--bot-only requires --only-unaddressed",
            file=sys.stderr,
        )
        return 1

    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved["Owner"]
    repo = resolved["Repo"]

    result = get_pr_review_comments(
        owner,
        repo,
        args.pull_request,
        author=args.author,
        include_diff_hunk=args.include_diff_hunk,
        include_issue_comments=args.include_issue_comments,
        detect_stale=args.detect_stale,
        exclude_stale=args.exclude_stale,
        only_stale=args.only_stale,
        group_by_domain=args.group_by_domain,
        only_unaddressed=args.only_unaddressed,
        bot_only=args.bot_only,
    )

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
