#!/usr/bin/env python3
"""Report open PRs that may be superseded by work already on main (issue #4355).

For each open PR, reports:
- Base distance in commits (how far behind main)
- Linked issue state (open/closed)
- Flags the closed-issue-plus-open-PR combination

Exit code is always 0: this is a proposal report, not a gate.
Auto-close on this signal alone would be wrong (see issue #4355 for false-
positive analysis). A human or agent must confirm before closing.

Usage:
    python scripts/report_pr_supersession.py --owner rjmurillo --repo ai-agents
    python scripts/report_pr_supersession.py --limit 50
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.github_core.api import resolve_repo_params  # noqa: E402


def _run_gh(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _sleep() -> None:
    time.sleep(0.4)


def _get_open_prs(owner: str, repo: str, limit: int) -> list[dict]:
    """Fetch open PRs via REST. Returns list of minimal PR dicts."""
    result = _run_gh([
        "api",
        f"repos/{owner}/{repo}/pulls",
        "--method", "GET",
        "-f", "state=open",
        "-f", f"per_page={min(limit, 100)}",
        "-f", "sort=updated",
        "-f", "direction=desc",
    ])
    if result.returncode != 0:
        print(f"ERROR: Failed to fetch PRs: {result.stderr}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print("ERROR: Failed to parse PR list", file=sys.stderr)
        return []


def _get_closing_issues(owner: str, repo: str, pr_number: int) -> list[int]:
    """Return issue numbers that the PR is linked to close via GraphQL."""
    query = (
        f'{{repository(owner:"{owner}",name:"{repo}")'
        f'{{pullRequest(number:{pr_number})'
        f'{{closingIssuesReferences(first:10){{nodes{{number}}}}}}}}}}'
    )
    result = _run_gh(["api", "graphql", "-f", f"query={query}"])
    _sleep()
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
        nodes = (
            data.get("data", {})
            .get("repository", {})
            .get("pullRequest", {})
            .get("closingIssuesReferences", {})
            .get("nodes", [])
        )
        return [n["number"] for n in nodes if n]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def _get_issue_state(owner: str, repo: str, issue_number: int) -> str:
    """Return 'open', 'closed', or 'unknown'."""
    result = _run_gh(["api", f"repos/{owner}/{repo}/issues/{issue_number}"])
    _sleep()
    if result.returncode != 0:
        return "unknown"
    try:
        data = json.loads(result.stdout)
        return data.get("state", "unknown")
    except (json.JSONDecodeError, KeyError):
        return "unknown"


def _commits_behind(owner: str, repo: str, base: str, head: str) -> int | None:
    """Return how many commits head is behind base, or None on error."""
    result = _run_gh([
        "api",
        f"repos/{owner}/{repo}/compare/{base}...{head}",
    ])
    _sleep()
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        return data.get("behind_by")
    except (json.JSONDecodeError, KeyError):
        return None


def _build_report(owner: str, repo: str, prs: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for pr in prs:
        number = pr.get("number", 0)
        title = pr.get("title", "")
        base_ref = (pr.get("base") or {}).get("ref", "")
        head_sha = (pr.get("head") or {}).get("sha", "")

        # Distance from base branch
        behind = _commits_behind(owner, repo, base_ref, head_sha) if base_ref and head_sha else None

        # Closing issues
        closing_issues = _get_closing_issues(owner, repo, number)

        # Issue states
        issue_details: list[dict] = []
        for iss_num in closing_issues:
            state = _get_issue_state(owner, repo, iss_num)
            issue_details.append({"number": iss_num, "state": state})

        closed_issues = [i for i in issue_details if i["state"] == "closed"]
        flag = bool(closed_issues)

        rows.append({
            "pr": number,
            "title": title,
            "base_branch": base_ref,
            "commits_behind": behind,
            "closing_issues": issue_details,
            "flag_closed_issue_open_pr": flag,
        })

    return rows


def _print_report(rows: list[dict], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(rows, indent=2))
        return

    flagged = [r for r in rows if r["flag_closed_issue_open_pr"]]
    clean = [r for r in rows if not r["flag_closed_issue_open_pr"]]

    print(f"\nPR Supersession Report: {len(rows)} open PRs examined")
    print(f"Flagged (closed issue + open PR): {len(flagged)}")

    if flagged:
        print("\n=== FLAGGED (require human review) ===")
        for r in flagged:
            behind_str = str(r["commits_behind"]) if r["commits_behind"] is not None else "?"
            closed_nums = [str(i["number"]) for i in r["closing_issues"] if i["state"] == "closed"]
            print(
                f"  PR #{r['pr']}: {r['title'][:70]}"
                f"\n    base: {r['base_branch']}, behind: {behind_str} commits"
                f"\n    closed issues: {', '.join('#' + n for n in closed_nums)}"
            )

    if clean:
        print("\n=== CLEAN (no closed linked issues) ===")
        for r in clean:
            behind_str = str(r["commits_behind"]) if r["commits_behind"] is not None else "?"
            issue_str = (
                ", ".join(f"#{i['number']}({i['state']})" for i in r["closing_issues"])
                or "none"
            )
            print(
                f"  PR #{r['pr']}: {r['title'][:60]}"
                f" | behind: {behind_str} | issues: {issue_str}"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report open PRs that may be superseded (issue #4355)."
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--limit", type=int, default=30,
        help="Maximum number of open PRs to examine (default: 30)",
    )
    parser.add_argument(
        "--output-format", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    print(f"Fetching up to {args.limit} open PRs from {owner}/{repo}...", file=sys.stderr)
    prs = _get_open_prs(owner, repo, args.limit)
    if not prs:
        print("No open PRs found or fetch failed.", file=sys.stderr)
        return 0

    print(f"Examining {len(prs)} PRs...", file=sys.stderr)
    rows = _build_report(owner, repo, prs)
    _print_report(rows, args.output_format)

    # Exit 0 always: this is a proposal, not a gate (issue #4355).
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
