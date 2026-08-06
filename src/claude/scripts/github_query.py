#!/usr/bin/env python3
"""Read-only GitHub query tool for the analyst agent.

Bundled inside the claude-agents plugin so the analyst can query GitHub
without cross-plugin script execution.  Every operation is read-only and
delegates to ``gh api`` (already allow-listed via ``Bash(gh *)``).

Usage::

    python3 "$CLAUDE_PLUGIN_ROOT/scripts/github_query.py" <command> [options]

Commands::

    pr-context       --pull-request <N>     PR metadata (title, body, state, ...)
    pr-threads       --pull-request <N>     Review threads with resolution status
    pr-comments      --pull-request <N>     Review + issue comments
    pr-checks        --pull-request <N>     CI check-run results
    issue-context    --issue <N>            Issue metadata

All output is JSON on stdout.  Errors go to stderr with non-zero exit.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gh_api(endpoint: str, *, method: str = "GET", paginate: bool = False) -> Any:
    """Call ``gh api`` and return parsed JSON."""
    cmd = ["gh", "api", endpoint, "--method", method]
    if paginate:
        cmd.append("--paginate")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"gh api error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    if not result.stdout.strip():
        return []
    return json.loads(result.stdout)


def _gh_graphql(query: str, variables: dict[str, Any] | None = None) -> Any:
    """Call ``gh api graphql`` and return parsed JSON."""
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    if variables:
        for k, v in variables.items():
            cmd.extend(["-f", f"{k}={v}"])
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"gh graphql error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def _repo_nwo() -> str:
    """Return owner/repo from the current git remote."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print("Cannot determine repository", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_pr_context(args: argparse.Namespace) -> None:
    """Fetch PR metadata."""
    nwo = _repo_nwo()
    data = _gh_api(f"/repos/{nwo}/pulls/{args.pull_request}")
    out = {
        "Number": data["number"],
        "Title": data["title"],
        "State": data["state"],
        "Author": data["user"]["login"],
        "HeadRef": data["head"]["ref"],
        "BaseRef": data["base"]["ref"],
        "Body": data.get("body", ""),
        "CreatedAt": data["created_at"],
        "UpdatedAt": data["updated_at"],
        "Mergeable": data.get("mergeable"),
        "Labels": [l["name"] for l in data.get("labels", [])],
    }
    json.dump(out, sys.stdout, indent=2)


def cmd_pr_threads(args: argparse.Namespace) -> None:
    """Fetch PR review threads with resolution status."""
    nwo = _repo_nwo()
    owner, repo = nwo.split("/")
    query = """
    query($owner: String!, $repo: String!, $pr: Int!, $cursor: String) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $pr) {
          reviewThreads(first: 100, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              isResolved
              isOutdated
              path
              line
              comments(first: 10) {
                nodes { author { login } body createdAt }
              }
            }
          }
        }
      }
    }
    """
    data = _gh_graphql(query, {
        "owner": owner, "repo": repo, "pr": str(args.pull_request),
    })
    threads = data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    out = {
        "TotalThreads": len(threads),
        "UnresolvedCount": sum(1 for t in threads if not t["isResolved"]),
        "Threads": threads,
    }
    json.dump(out, sys.stdout, indent=2)


def cmd_pr_comments(args: argparse.Namespace) -> None:
    """Fetch PR review comments and optionally issue comments."""
    nwo = _repo_nwo()
    review = _gh_api(f"/repos/{nwo}/pulls/{args.pull_request}/comments", paginate=True)
    comments = []
    for c in review:
        comments.append({
            "Id": c["id"],
            "CommentType": "Review",
            "Author": c["user"]["login"],
            "Path": c.get("path"),
            "Line": c.get("line") or c.get("original_line"),
            "Body": c["body"],
            "CreatedAt": c["created_at"],
            "InReplyToId": c.get("in_reply_to_id"),
        })
    issue = _gh_api(f"/repos/{nwo}/issues/{args.pull_request}/comments", paginate=True)
    for c in issue:
        comments.append({
            "Id": c["id"],
            "CommentType": "Issue",
            "Author": c["user"]["login"],
            "Path": None,
            "Line": None,
            "Body": c["body"],
            "CreatedAt": c["created_at"],
            "InReplyToId": None,
        })
    out = {"TotalComments": len(comments), "Comments": comments}
    json.dump(out, sys.stdout, indent=2)


def cmd_pr_checks(args: argparse.Namespace) -> None:
    """Fetch CI check results for a PR."""
    nwo = _repo_nwo()
    owner, repo = nwo.split("/")
    query = """
    query($owner: String!, $repo: String!, $pr: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $pr) {
          commits(last: 1) {
            nodes {
              commit {
                statusCheckRollup {
                  contexts(first: 100) {
                    nodes {
                      ... on CheckRun {
                        name
                        conclusion
                        status
                        detailsUrl
                      }
                      ... on StatusContext {
                        context
                        state
                        targetUrl
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
    """
    data = _gh_graphql(query, {
        "owner": owner, "repo": repo, "pr": str(args.pull_request),
    })
    commits = data["data"]["repository"]["pullRequest"]["commits"]["nodes"]
    if not commits:
        json.dump({"Checks": [], "AllPassing": True}, sys.stdout, indent=2)
        return
    rollup = commits[0]["commit"].get("statusCheckRollup")
    if not rollup:
        json.dump({"Checks": [], "AllPassing": True}, sys.stdout, indent=2)
        return
    checks = []
    for ctx in rollup["contexts"]["nodes"]:
        if "name" in ctx:
            checks.append({
                "Name": ctx["name"],
                "Conclusion": ctx.get("conclusion"),
                "Status": ctx.get("status"),
                "DetailsUrl": ctx.get("detailsUrl"),
            })
        elif "context" in ctx:
            checks.append({
                "Name": ctx["context"],
                "Conclusion": ctx.get("state"),
                "Status": ctx.get("state"),
                "DetailsUrl": ctx.get("targetUrl"),
            })
    failed = [c for c in checks if c["Conclusion"] not in (
        "SUCCESS", "NEUTRAL", "SKIPPED", None,
    )]
    out = {
        "TotalChecks": len(checks),
        "PassedCount": len(checks) - len(failed),
        "FailedCount": len(failed),
        "AllPassing": len(failed) == 0,
        "Checks": checks,
    }
    json.dump(out, sys.stdout, indent=2)


def cmd_issue_context(args: argparse.Namespace) -> None:
    """Fetch issue metadata."""
    nwo = _repo_nwo()
    data = _gh_api(f"/repos/{nwo}/issues/{args.issue}")
    out = {
        "Number": data["number"],
        "Title": data["title"],
        "State": data["state"],
        "Author": data["user"]["login"],
        "Body": data.get("body", ""),
        "Labels": [l["name"] for l in data.get("labels", [])],
        "CreatedAt": data["created_at"],
        "UpdatedAt": data["updated_at"],
    }
    json.dump(out, sys.stdout, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only GitHub queries for the analyst agent.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("pr-context")
    p.add_argument("--pull-request", type=int, required=True)

    p = sub.add_parser("pr-threads")
    p.add_argument("--pull-request", type=int, required=True)

    p = sub.add_parser("pr-comments")
    p.add_argument("--pull-request", type=int, required=True)

    p = sub.add_parser("pr-checks")
    p.add_argument("--pull-request", type=int, required=True)

    p = sub.add_parser("issue-context")
    p.add_argument("--issue", type=int, required=True)

    args = parser.parse_args()
    handlers = {
        "pr-context": cmd_pr_context,
        "pr-threads": cmd_pr_threads,
        "pr-comments": cmd_pr_comments,
        "pr-checks": cmd_pr_checks,
        "issue-context": cmd_issue_context,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
