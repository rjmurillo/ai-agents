#!/usr/bin/env python3
"""Read the native relationships of a GitHub Issue.

Returns the parent, sub-issues, blocked-by, blocking, and relates-to links
that GitHub stores on the issue. These are the platform relationships, not
"#123" mentions in the body. See references/issue-relationships.md.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Not found (no issue with that number) or plugin lib missing
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import os
import sys

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    gh_graphql,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

SCRIPT_NAME = "get_issue_relationships.py"

# One page of 100 covers every issue seen in practice; the response reports
# totalCount so a caller can tell when a list was cut short.
_NODE = "number title state url repository { nameWithOwner }"
RELATIONSHIPS_QUERY = f"""
query($owner: String!, $repo: String!, $number: Int!) {{
  repository(owner: $owner, name: $repo) {{
    issue(number: $number) {{
      id
      number
      title
      state
      parent {{ {_NODE} }}
      subIssues(first: 100) {{ totalCount nodes {{ {_NODE} }} }}
      blockedBy(first: 100) {{ totalCount nodes {{ {_NODE} }} }}
      blocking(first: 100) {{ totalCount nodes {{ {_NODE} }} }}
      relatesTo(first: 100) {{ totalCount nodes {{ {_NODE} }} }}
    }}
  }}
}}
"""

LIST_FIELDS = (
    ("subIssues", "sub_issues"),
    ("blockedBy", "blocked_by"),
    ("blocking", "blocking"),
    ("relatesTo", "relates_to"),
)


class IssueNotFoundError(RuntimeError):
    """The repository has no issue with the requested number."""


def query_or_not_found(query: str, variables: dict, label: str) -> dict:
    """Run a GraphQL query, mapping GitHub's unresolved-number error to not found.

    GitHub answers an unknown issue number with a GraphQL error ("Could not
    resolve to an issue"), not a null node, so gh_graphql raises.
    """
    try:
        return gh_graphql(query, variables)
    except RuntimeError as exc:
        if "Could not resolve to" in str(exc):
            raise IssueNotFoundError(f"{label} not found") from exc
        raise


def _flatten(node: dict) -> dict:
    return {
        "number": node["number"],
        "title": node["title"],
        "state": node["state"],
        "url": node["url"],
        "repository": node["repository"]["nameWithOwner"],
    }


def fetch_relationships(owner: str, repo: str, number: int) -> dict:
    """Return the issue's node id and its native relationships.

    Raises:
        IssueNotFoundError: The number is not an issue in owner/repo.
        RuntimeError: The GraphQL call failed.
    """
    data = query_or_not_found(
        RELATIONSHIPS_QUERY,
        {"owner": owner, "repo": repo, "number": number},
        f"Issue #{number} in {owner}/{repo}",
    )
    issue = (data.get("repository") or {}).get("issue")
    if not issue:
        raise IssueNotFoundError(f"Issue #{number} not found in {owner}/{repo}")
    result: dict = {
        "id": issue["id"],
        "number": issue["number"],
        "title": issue["title"],
        "state": issue["state"],
        "parent": _flatten(issue["parent"]) if issue.get("parent") else None,
    }
    for gql_name, key in LIST_FIELDS:
        connection = issue[gql_name]
        result[key] = [_flatten(n) for n in connection["nodes"]]
        result[f"{key}_total"] = connection["totalCount"]
    return result


def _summary(rel: dict) -> str:
    parent = f"#{rel['parent']['number']}" if rel["parent"] else "none"
    counts = ", ".join(f"{key} {rel[f'{key}_total']}" for _, key in LIST_FIELDS)
    return f"Issue #{rel['number']}: parent {parent}, {counts}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read the native relationships of a GitHub Issue.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)
    if args.issue <= 0:
        write_skill_error(
            "--issue must be a positive integer",
            1,
            error_type="InvalidParams",
            output_format=fmt,
            script_name=SCRIPT_NAME,
        )
        return 1

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    try:
        rel = fetch_relationships(resolved.owner, resolved.repo, args.issue)
    except IssueNotFoundError as exc:
        write_skill_error(
            str(exc),
            2,
            error_type="NotFound",
            output_format=fmt,
            script_name=SCRIPT_NAME,
        )
        return 2
    except RuntimeError as exc:
        write_skill_error(
            str(exc) or "GraphQL request failed",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name=SCRIPT_NAME,
        )
        return 3

    rel.pop("id")
    write_skill_output(
        rel,
        output_format=fmt,
        human_summary=_summary(rel),
        status="PASS",
        script_name=SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
