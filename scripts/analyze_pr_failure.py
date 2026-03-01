#!/usr/bin/env python3
"""Analyze a GitHub Pull Request for retrospective data gathering.

Extracts structured metrics from a PR to bootstrap retrospective Phase 0
(Data Gathering). Outputs JSON with PR metrics, comment distribution,
file distribution, review timeline, and synthesis panel references.

Inputs:
    --pr: PR number (required)
    --owner/--repo: Repository coordinates (auto-detected from git remote)
    --format: Output format, "json" (default) or "markdown"

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - PR not found
    3 - External error (API failure)

See: Issue #940
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Bot login suffixes used to classify comment authors
_BOT_SUFFIXES = ("[bot]", "-bot")


def _run_gh(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    """Run a gh CLI command and return the result."""
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _resolve_repo(owner: str, repo: str) -> tuple[str, str]:
    """Resolve owner/repo from arguments or git remote."""
    if owner and repo:
        return owner, repo

    result = _run_gh(["repo", "view", "--json", "owner,name"])
    if result.returncode != 0:
        print("ERROR: Cannot detect repository. Use --owner and --repo.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(result.stdout)
    return data["owner"]["login"], data["name"]


def _is_bot(login: str) -> bool:
    """Return True if the login looks like a bot account."""
    lower = login.lower()
    return any(lower.endswith(suffix) for suffix in _BOT_SUFFIXES)


def fetch_pr_metadata(owner: str, repo: str, pr_number: int) -> dict:
    """Fetch core PR metadata via gh CLI."""
    fields = (
        "number,title,state,author,createdAt,updatedAt,mergedAt,"
        "additions,deletions,changedFiles,commits,labels,baseRefName,headRefName"
    )
    result = _run_gh([
        "pr", "view", str(pr_number),
        "--repo", f"{owner}/{repo}",
        "--json", fields,
    ])

    if result.returncode != 0:
        err = result.stderr or result.stdout
        if "not found" in err.lower():
            print(f"ERROR: PR #{pr_number} not found in {owner}/{repo}", file=sys.stderr)
            sys.exit(2)
        print(f"ERROR: Failed to fetch PR: {err}", file=sys.stderr)
        sys.exit(3)

    return json.loads(result.stdout)


def fetch_pr_comments(owner: str, repo: str, pr_number: int) -> list[dict]:
    """Fetch issue-level comments on the PR."""
    result = _run_gh([
        "api", f"repos/{owner}/{repo}/issues/{pr_number}/comments",
        "--paginate",
    ], timeout=60)

    if result.returncode != 0:
        err = result.stderr or result.stdout
        print(f"ERROR: Failed to fetch PR comments: {err}", file=sys.stderr)
        sys.exit(3)

    return json.loads(result.stdout)


def fetch_pr_reviews(owner: str, repo: str, pr_number: int) -> list[dict]:
    """Fetch review events for the PR."""
    result = _run_gh([
        "api", f"repos/{owner}/{repo}/pulls/{pr_number}/reviews",
        "--paginate",
    ], timeout=60)

    if result.returncode != 0:
        err = result.stderr or result.stdout
        print(f"ERROR: Failed to fetch PR reviews: {err}", file=sys.stderr)
        sys.exit(3)

    return json.loads(result.stdout)


def fetch_pr_files(owner: str, repo: str, pr_number: int) -> list[dict]:
    """Fetch the list of changed files with stats."""
    result = _run_gh([
        "api", f"repos/{owner}/{repo}/pulls/{pr_number}/files",
        "--paginate",
    ], timeout=60)

    if result.returncode != 0:
        err = result.stderr or result.stdout
        print(f"ERROR: Failed to fetch PR files: {err}", file=sys.stderr)
        sys.exit(3)

    return json.loads(result.stdout)


def build_comment_distribution(comments: list[dict]) -> dict:
    """Classify comments into bot vs human with author counts."""
    bot_count = 0
    human_count = 0
    authors: Counter[str] = Counter()

    for comment in comments:
        login = comment.get("user", {}).get("login", "unknown")
        authors[login] += 1
        if _is_bot(login):
            bot_count += 1
        else:
            human_count += 1

    return {
        "total": len(comments),
        "bot_count": bot_count,
        "human_count": human_count,
        "authors": dict(authors.most_common()),
    }


def build_file_distribution(files: list[dict]) -> dict:
    """Group changed files by top-level directory."""
    distribution: Counter[str] = Counter()

    for f in files:
        filename = f.get("filename", "")
        parts = filename.split("/")
        directory = parts[0] if len(parts) > 1 else "(root)"
        distribution[directory] += 1

    return dict(distribution.most_common())


def build_review_timeline(reviews: list[dict]) -> list[dict]:
    """Extract review events as a timeline."""
    timeline = []
    for review in reviews:
        login = review.get("user", {}).get("login", "unknown")
        timeline.append({
            "author": login,
            "state": review.get("state", "UNKNOWN"),
            "submitted_at": review.get("submitted_at", ""),
        })

    return sorted(timeline, key=lambda r: r.get("submitted_at", ""))


def find_synthesis_panels(owner: str, repo: str, pr_number: int) -> list[str]:
    """Search for synthesis panel documents related to this PR."""
    patterns = [
        f".agents/retrospective/*pr-{pr_number}*",
        f".agents/retrospective/*PR-{pr_number}*",
    ]

    matches = []
    for pattern in patterns:
        result = subprocess.run(
            ["git", "ls-files", pattern],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                if line and line not in matches:
                    matches.append(line)

    return matches


def analyze_pr(owner: str, repo: str, pr_number: int) -> dict:
    """Run full analysis on a PR and return structured results."""
    pr_data = fetch_pr_metadata(owner, repo, pr_number)
    comments = fetch_pr_comments(owner, repo, pr_number)
    reviews = fetch_pr_reviews(owner, repo, pr_number)
    files = fetch_pr_files(owner, repo, pr_number)

    commits = pr_data.get("commits", [])
    commit_count = len(commits) if isinstance(commits, list) else 0

    return {
        "pr_number": pr_data.get("number", pr_number),
        "title": pr_data.get("title", ""),
        "state": pr_data.get("state", ""),
        "author": pr_data.get("author", {}).get("login", ""),
        "base_branch": pr_data.get("baseRefName", ""),
        "head_branch": pr_data.get("headRefName", ""),
        "created_at": pr_data.get("createdAt", ""),
        "updated_at": pr_data.get("updatedAt", ""),
        "merged_at": pr_data.get("mergedAt"),
        "labels": [label.get("name", "") for label in pr_data.get("labels", [])],
        "metrics": {
            "commits": commit_count,
            "files_changed": pr_data.get("changedFiles", 0),
            "additions": pr_data.get("additions", 0),
            "deletions": pr_data.get("deletions", 0),
        },
        "comment_distribution": build_comment_distribution(comments),
        "file_distribution": build_file_distribution(files),
        "review_timeline": build_review_timeline(reviews),
        "synthesis_panels": find_synthesis_panels(owner, repo, pr_number),
    }


def format_markdown(analysis: dict) -> str:
    """Format the analysis as markdown for human consumption."""
    lines = []
    lines.append(f"# PR #{analysis['pr_number']}: {analysis['title']}")
    lines.append("")
    lines.append(f"**State:** {analysis['state']}  ")
    lines.append(f"**Author:** {analysis['author']}  ")
    lines.append(f"**Branch:** {analysis['head_branch']} -> {analysis['base_branch']}  ")
    lines.append(f"**Created:** {analysis['created_at']}  ")
    if analysis.get("merged_at"):
        lines.append(f"**Merged:** {analysis['merged_at']}  ")
    lines.append("")

    m = analysis["metrics"]
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Commits | {m['commits']} |")
    lines.append(f"| Files changed | {m['files_changed']} |")
    lines.append(f"| Additions | {m['additions']} |")
    lines.append(f"| Deletions | {m['deletions']} |")
    lines.append("")

    cd = analysis["comment_distribution"]
    lines.append("## Comment Distribution")
    lines.append("")
    lines.append(f"- Total: {cd['total']}")
    lines.append(f"- Bot: {cd['bot_count']}")
    lines.append(f"- Human: {cd['human_count']}")
    if cd.get("authors"):
        lines.append("")
        lines.append("| Author | Count |")
        lines.append("|--------|-------|")
        for author, count in cd["authors"].items():
            lines.append(f"| {author} | {count} |")
    lines.append("")

    fd = analysis["file_distribution"]
    if fd:
        lines.append("## File Distribution")
        lines.append("")
        lines.append("| Directory | Files |")
        lines.append("|-----------|-------|")
        for directory, count in fd.items():
            lines.append(f"| {directory} | {count} |")
        lines.append("")

    timeline = analysis["review_timeline"]
    if timeline:
        lines.append("## Review Timeline")
        lines.append("")
        lines.append("| Time | Reviewer | State |")
        lines.append("|------|----------|-------|")
        for event in timeline:
            lines.append(
                f"| {event['submitted_at']} | {event['author']} | {event['state']} |"
            )
        lines.append("")

    panels = analysis["synthesis_panels"]
    if panels:
        lines.append("## Synthesis Panels")
        lines.append("")
        for panel in panels:
            lines.append(f"- `{panel}`")
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pr", type=int, required=True,
        help="Pull request number to analyze",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--format", choices=["json", "markdown"], default="json",
        dest="output_format",
        help="Output format (default: json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Returns:
        0 on success, non-zero on failure (per ADR-035).
    """
    args = build_parser().parse_args(argv)
    owner, repo = _resolve_repo(args.owner, args.repo)
    analysis = analyze_pr(owner, repo, args.pr)

    if args.output_format == "markdown":
        print(format_markdown(analysis))
    else:
        print(json.dumps(analysis, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
