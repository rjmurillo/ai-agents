"""Homework Scanner - Detect deferred work items in merged PR comments.

Scans PR review comments and review bodies for patterns indicating deferred
work (TODO, follow-up, out of scope, future improvement). Outputs structured
JSON for downstream issue creation.

Exit Codes (ADR-035):
    0 - Success (with or without homework items found)
    2 - Configuration or input error
    3 - External service error (GitHub API failure)

Standards:
    - ADR-006: Business logic in scripts, not workflow YAML
    - ADR-042: Python-first for new scripts
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

# Patterns that indicate deferred work in PR comments.
# Order: most specific first to reduce false positives.
HOMEWORK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"deferred\s+to\s+follow[- ]?up", re.IGNORECASE),
    re.compile(r"future\s+improvement", re.IGNORECASE),
    re.compile(r"a\s+future\s+improvement\s+could\s+be", re.IGNORECASE),
    re.compile(r"out\s+of\s+scope\s+for\s+this\s+PR", re.IGNORECASE),
    re.compile(r"addressed\s+in\s+a\s+future\s+PR", re.IGNORECASE),
    re.compile(r"follow[- ]?up\s+task", re.IGNORECASE),
    re.compile(r"\bTODO\b[:\s]", re.MULTILINE),
]

# Patterns that produce false positives. If a comment matches both a homework
# pattern and a false-positive pattern, it is excluded.
FALSE_POSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"TODO.*in bot failure", re.IGNORECASE),
    re.compile(r"nitpick.*already addressed", re.IGNORECASE),
    re.compile(r"^\s*>\s*TODO", re.MULTILINE),  # Quoted TODOs (citations)
    re.compile(r"```.*TODO.*```", re.DOTALL),  # TODOs inside code blocks
]


@dataclass
class HomeworkItem:
    """A detected homework item from a PR comment."""

    pr_number: int
    comment_id: int
    author: str
    body_excerpt: str
    matched_pattern: str
    comment_url: str
    source_type: str  # "review_comment" or "review_body"


@dataclass
class ScanResult:
    """Result of scanning a PR for homework items."""

    pr_number: int
    items: list[HomeworkItem] = field(default_factory=list)
    comments_scanned: int = 0
    error: str | None = None


def is_false_positive(text: str) -> bool:
    """Check if text matches a known false-positive pattern."""
    return any(pattern.search(text) for pattern in FALSE_POSITIVE_PATTERNS)


def find_homework_in_text(text: str) -> str | None:
    """Return the first matching homework pattern name, or None."""
    for pattern in HOMEWORK_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None


def extract_excerpt(body: str, max_length: int = 200) -> str:
    """Extract a meaningful excerpt from the comment body."""
    # Strip leading/trailing whitespace and collapse internal whitespace
    cleaned = re.sub(r"\s+", " ", body.strip())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[:max_length] + "..."


def fetch_pr_comments(
    owner: str, repo: str, pr_number: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch review comments and reviews for a PR via gh CLI.

    Returns:
        Tuple of (review_comments, reviews).

    Raises:
        RuntimeError: If gh CLI call fails.
    """
    review_comments = _gh_api(
        f"repos/{owner}/{repo}/pulls/{pr_number}/comments"
    )
    reviews = _gh_api(f"repos/{owner}/{repo}/pulls/{pr_number}/reviews")
    return review_comments, reviews


def _gh_api(endpoint: str) -> list[dict[str, Any]]:
    """Call gh api and return parsed JSON list."""
    result = subprocess.run(
        ["gh", "api", endpoint, "--paginate"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = f"gh api {endpoint} failed: {result.stderr.strip()}"
        raise RuntimeError(msg)
    raw = result.stdout.strip()
    if not raw:
        return []
    parsed = json.loads(raw)
    if isinstance(parsed, list):
        return parsed
    return [parsed]


def scan_pr(owner: str, repo: str, pr_number: int) -> ScanResult:
    """Scan a single PR for homework items."""
    scan = ScanResult(pr_number=pr_number)

    try:
        review_comments, reviews = fetch_pr_comments(owner, repo, pr_number)
    except RuntimeError as exc:
        scan.error = str(exc)
        return scan

    # Scan review comments (inline code comments)
    for comment in review_comments:
        body = str(comment.get("body", ""))
        scan.comments_scanned += 1
        matched = find_homework_in_text(body)
        if matched and not is_false_positive(body):
            comment_id = int(comment.get("id", 0))
            scan.items.append(
                HomeworkItem(
                    pr_number=pr_number,
                    comment_id=comment_id,
                    author=str(comment.get("user", {}).get("login", "unknown")),
                    body_excerpt=extract_excerpt(body),
                    matched_pattern=matched,
                    comment_url=str(comment.get("html_url", "")),
                    source_type="review_comment",
                )
            )

    # Scan review bodies (top-level review summaries)
    for review in reviews:
        body = str(review.get("body", ""))
        if not body or body == "None":
            continue
        scan.comments_scanned += 1
        matched = find_homework_in_text(body)
        if matched and not is_false_positive(body):
            review_id = int(review.get("id", 0))
            scan.items.append(
                HomeworkItem(
                    pr_number=pr_number,
                    comment_id=review_id,
                    author=str(
                        review.get("user", {}).get("login", "unknown")
                    ),
                    body_excerpt=extract_excerpt(body),
                    matched_pattern=matched,
                    comment_url=str(review.get("html_url", "")),
                    source_type="review_body",
                )
            )

    return scan


def build_issue_body(item: HomeworkItem, owner: str, repo: str) -> str:
    """Build the markdown body for a homework tracking issue."""
    return (
        f"## Source\n\n"
        f"From PR #{item.pr_number}, comment by @{item.author}:\n"
        f"{item.comment_url}\n\n"
        f"> {item.body_excerpt}\n\n"
        f"## Matched Pattern\n\n"
        f"`{item.matched_pattern}`\n\n"
        f"---\n"
        f"Created by Homework Scanner from PR #{item.pr_number}"
    )


def create_issues(
    items: list[HomeworkItem], owner: str, repo: str, *, dry_run: bool = False
) -> list[dict[str, Any]]:
    """Create GitHub issues for detected homework items.

    Returns:
        List of created issue metadata dicts.
    """
    created: list[dict[str, Any]] = []
    for item in items:
        title = (
            f"Homework: {item.body_excerpt[:80]}"
            if len(item.body_excerpt) > 80
            else f"Homework: {item.body_excerpt}"
        )
        body = build_issue_body(item, owner, repo)

        if dry_run:
            created.append(
                {
                    "title": title,
                    "body": body,
                    "labels": ["homework", "enhancement"],
                    "dry_run": True,
                }
            )
            continue

        result = subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--repo",
                f"{owner}/{repo}",
                "--title",
                title,
                "--body",
                body,
                "--label",
                "homework,enhancement",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            issue_url = result.stdout.strip()
            created.append({"title": title, "url": issue_url})
        else:
            created.append(
                {"title": title, "error": result.stderr.strip()}
            )

    return created


def parse_repo_string(repo_str: str) -> tuple[str, str]:
    """Parse 'owner/repo' into (owner, repo) tuple."""
    parts = repo_str.split("/")
    if len(parts) != 2:
        msg = f"Invalid repo format '{repo_str}'. Expected 'owner/repo'."
        raise ValueError(msg)
    return parts[0], parts[1]


def main(args: Sequence[str] | None = None) -> int:
    """Entry point for homework scanner.

    Returns:
        Exit code per ADR-035.
    """
    parser = argparse.ArgumentParser(
        description="Scan merged PR comments for deferred homework items."
    )
    parser.add_argument(
        "--pr",
        type=int,
        required=True,
        help="PR number to scan.",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="Repository in owner/repo format. Defaults to GITHUB_REPOSITORY.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be created without creating issues.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Write JSON results to this file path.",
    )

    parsed = parser.parse_args(args)

    if not parsed.repo:
        print("Error: --repo or GITHUB_REPOSITORY required.", file=sys.stderr)
        return 2

    try:
        owner, repo = parse_repo_string(parsed.repo)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    scan = scan_pr(owner, repo, parsed.pr)

    if scan.error:
        print(f"Error scanning PR #{parsed.pr}: {scan.error}", file=sys.stderr)
        return 3

    result_data: dict[str, Any] = {
        "pr_number": scan.pr_number,
        "comments_scanned": scan.comments_scanned,
        "items_found": len(scan.items),
        "items": [asdict(item) for item in scan.items],
    }

    if scan.items:
        created = create_issues(
            scan.items, owner, repo, dry_run=parsed.dry_run
        )
        result_data["issues_created"] = created

    output_json = json.dumps(result_data, indent=2)

    if parsed.output:
        with open(parsed.output, "w") as f:
            f.write(output_json)
        print(f"Results written to {parsed.output}")
    else:
        print(output_json)

    print(
        f"Scanned {scan.comments_scanned} comments, "
        f"found {len(scan.items)} homework items."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
