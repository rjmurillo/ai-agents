#!/usr/bin/env python3
"""Add or remove a native relationship between GitHub Issues.

GitHub stores five issue relationships natively: parent, sub-issue,
blocked-by, blocking, and relates-to. A "#123" mention in an issue body
creates none of them. Use this script so the link shows in the issue
sidebar, the sub-issue progress bar, and the dependency graph.

Relations, read from the point of view of --issue:
    parent      --target is the parent of --issue (one target only)
    sub-issue   each --target becomes a child of --issue
    blocked-by  --issue is blocked by each --target
    blocking    --issue blocks each --target
    relates-to  --issue relates to each --target

The script is idempotent: an existing link is reported as already_linked,
and removing a missing link is reported as not_linked. Pull requests
cannot take part in these relationships and are rejected.

Exit codes follow ADR-035:
    0 - Success (including no-op)
    1 - Invalid parameters / logic error (bad target, PR target, parent conflict)
    2 - Not found (issue or target does not exist) or plugin lib missing
    3 - External error (API failure on any mutation)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Any

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
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from get_issue_relationships import (
    IssueNotFoundError,
    fetch_relationships,
    query_or_not_found,
)
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

SCRIPT_NAME = "set_issue_relationship.py"
RELATIONS = ("parent", "sub-issue", "blocked-by", "blocking", "relates-to")
_TARGET_RE = re.compile(r"^(?:(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+))?#?(?P<number>\d+)$")

TARGET_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issueOrPullRequest(number: $number) {
      __typename
      ... on Issue { id number parent { number repository { nameWithOwner } } }
    }
  }
}
"""

# relation -> (add mutation, remove mutation, first input field, second input
# field, source_is_first). source_is_first says whether --issue fills the
# first field; "parent" and "blocking" invert the pair.
_MUTATIONS = {
    "parent": ("addSubIssue", "removeSubIssue", "issueId", "subIssueId", False),
    "sub-issue": ("addSubIssue", "removeSubIssue", "issueId", "subIssueId", True),
    "blocked-by": ("addBlockedBy", "removeBlockedBy", "issueId", "blockingIssueId", True),
    "blocking": ("addBlockedBy", "removeBlockedBy", "issueId", "blockingIssueId", False),
    "relates-to": ("addRelatesTo", "removeRelatesTo", "issueId", "relatedIssueId", True),
}

# relation -> key in fetch_relationships() output that lists current links.
_CURRENT_KEY = {
    "sub-issue": "sub_issues",
    "blocked-by": "blocked_by",
    "blocking": "blocking",
    "relates-to": "relates_to",
}


class UsageError(ValueError):
    """The request is malformed or conflicts with current state (exit 1)."""


@dataclass(frozen=True)
class Target:
    owner: str
    repo: str
    number: int
    node_id: str = ""
    parent: str = ""

    @property
    def key(self) -> str:
        return f"{self.owner}/{self.repo}#{self.number}".lower()

    @property
    def label(self) -> str:
        return f"{self.owner}/{self.repo}#{self.number}"


def parse_target(text: str, owner: str, repo: str) -> Target:
    """Parse "123", "#123", or "owner/repo#123" into a Target."""
    match = _TARGET_RE.match(text.strip())
    if not match or int(match["number"]) <= 0:
        raise UsageError(f"Invalid target '{text}'. Use 123, #123, or owner/repo#123")
    return Target(match["owner"] or owner, match["repo"] or repo, int(match["number"]))


def resolve_target(target: Target) -> Target:
    """Look up the target's node id and parent; reject pull requests."""
    data = query_or_not_found(
        TARGET_QUERY,
        {"owner": target.owner, "repo": target.repo, "number": target.number},
        target.label,
    )
    node = (data.get("repository") or {}).get("issueOrPullRequest")
    if not node:
        raise IssueNotFoundError(f"{target.label} not found")
    if node["__typename"] != "Issue":
        raise UsageError(
            f"{target.label} is a pull request. Issue relationships link issues only; "
            "link a PR with a closing keyword in its body instead."
        )
    parent = node.get("parent")
    parent_label = f"{parent['repository']['nameWithOwner']}#{parent['number']}" if parent else ""
    return Target(target.owner, target.repo, target.number, node["id"], parent_label)


def validate_request(args: argparse.Namespace) -> None:
    if args.issue <= 0:
        raise UsageError("--issue must be a positive integer")
    if args.relation == "parent" and len(args.target) != 1:
        raise UsageError("--relation parent takes exactly one --target; an issue has one parent")
    if args.replace_parent and (args.remove or args.relation not in ("parent", "sub-issue")):
        raise UsageError("--replace-parent applies only when adding parent or sub-issue links")


def _linked_keys(relation: str, current: dict[str, Any]) -> set[str]:
    if relation == "parent":
        parent = current["parent"]
        return {f"{parent['repository']}#{parent['number']}".lower()} if parent else set()
    return {f"{n['repository']}#{n['number']}".lower() for n in current[_CURRENT_KEY[relation]]}


def _parent_conflict(
    relation: str, target: Target, current: dict[str, Any], source_label: str
) -> str:
    """Return the existing parent that blocks this add, or "" when none does."""
    if relation == "parent" and current["parent"]:
        return f"{current['parent']['repository']}#{current['parent']['number']}"
    if relation == "sub-issue" and target.parent and target.parent.lower() != source_label.lower():
        return target.parent
    return ""


def _mutation_text(relation: str, remove: bool, replace_parent: bool) -> str:
    add_name, remove_name, first, second, _ = _MUTATIONS[relation]
    name = remove_name if remove else add_name
    extra = ", replaceParent: true" if replace_parent and not remove else ""
    return (
        f"mutation($a: ID!, $b: ID!) {{ {name}(input: {{{first}: $a, {second}: $b{extra}}}) "
        "{ clientMutationId } }"
    )


def _mutation_ids(relation: str, source_id: str, target_id: str) -> dict[str, Any]:
    source_is_first = _MUTATIONS[relation][4]
    return {"a": source_id, "b": target_id} if source_is_first else {"a": target_id, "b": source_id}


def plan_action(
    args: argparse.Namespace, target: Target, current: dict[str, Any], source_label: str
) -> str:
    """Decide what to do for one target without calling the API."""
    linked = target.key in _linked_keys(args.relation, current)
    if args.remove:
        return "unlink" if linked else "not_linked"
    if linked:
        return "already_linked"
    conflict = _parent_conflict(args.relation, target, current, source_label)
    if conflict and not args.replace_parent:
        raise UsageError(
            f"Parent conflict: {conflict} is already the parent. "
            "An issue has one parent; pass --replace-parent to move it."
        )
    return "link"


def apply_target(
    args: argparse.Namespace, target: Target, current: dict[str, Any], source_label: str
) -> dict[str, Any]:
    action = plan_action(args, target, current, source_label)
    row = {"target": target.label, "number": target.number, "action": action}
    if action not in ("link", "unlink"):
        return row
    if args.dry_run:
        row["action"] = f"would_{action}"
        return row
    try:
        gh_graphql(
            _mutation_text(args.relation, args.remove, args.replace_parent),
            _mutation_ids(args.relation, current["id"], target.node_id),
        )
    except RuntimeError as exc:
        row["action"] = "failed"
        row["error"] = str(exc) or "GraphQL mutation failed"
        return row
    row["action"] = "linked" if action == "link" else "unlinked"
    return row


def run(args: argparse.Namespace, owner: str, repo: str) -> dict[str, Any]:
    validate_request(args)
    source_label = f"{owner}/{repo}#{args.issue}"
    targets = [parse_target(t, owner, repo) for t in args.target]
    if any(t.key == source_label.lower() for t in targets):
        raise UsageError("An issue cannot be linked to itself")
    current = fetch_relationships(owner, repo, args.issue)
    resolved = [resolve_target(t) for t in targets]
    results = [apply_target(args, t, current, source_label) for t in resolved]
    return {
        "issue": args.issue,
        "relation": args.relation,
        "remove": args.remove,
        "dry_run": args.dry_run,
        "results": results,
        "failed": [r["target"] for r in results if r["action"] == "failed"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add or remove a native relationship between GitHub Issues.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--issue", type=int, required=True, help="Issue number the relation is read from"
    )
    parser.add_argument("--relation", required=True, choices=RELATIONS, help="Relationship type")
    parser.add_argument(
        "--target",
        nargs="+",
        required=True,
        help="Related issue(s): 123, #123, or owner/repo#123",
    )
    parser.add_argument(
        "--remove", action="store_true", help="Remove the link instead of adding it"
    )
    parser.add_argument(
        "--replace-parent",
        action="store_true",
        help="Move the child from its current parent (parent and sub-issue only)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report planned changes; call no mutation"
    )
    add_output_format_arg(parser)
    return parser


def _error(message: str, code: int, error_type: str, fmt: str) -> int:
    write_skill_error(
        message, code, error_type=error_type, output_format=fmt, script_name=SCRIPT_NAME
    )
    return code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)
    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    try:
        data = run(args, resolved.owner, resolved.repo)
    except UsageError as exc:
        return _error(str(exc), 1, "InvalidParams", fmt)
    except IssueNotFoundError as exc:
        return _error(str(exc), 2, "NotFound", fmt)
    except RuntimeError as exc:
        return _error(str(exc) or "GraphQL request failed", 3, "ApiError", fmt)

    if data["failed"]:
        write_skill_error(
            f"Failed to update: {', '.join(data['failed'])}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name=SCRIPT_NAME,
            extra=data,
        )
        return 3
    actions = ", ".join(f"{r['target']} {r['action']}" for r in data["results"])
    write_skill_output(
        data,
        output_format=fmt,
        status="PASS",
        script_name=SCRIPT_NAME,
        human_summary=f"#{args.issue} {args.relation}: {actions}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
