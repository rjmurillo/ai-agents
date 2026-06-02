#!/usr/bin/env python3
"""Check if a GitHub Pull Request has been merged.

Queries GitHub GraphQL API to determine PR merge state.
Use this before starting PR review work to prevent wasted effort on merged PRs.
Per Skill-PR-Review-007: gh pr view may return stale data.

Exit codes follow ADR-035:
    0   - PR is NOT merged (safe to proceed with review)
    2   - Error occurred (config/parse error)
    3   - External error (API failure)
    4   - Auth error
    100 - PR IS merged (script-specific: skip review work)

The exit-100 sentinel is intentional for the pre-review skip-check use case
(Skill-PR-Review-007). Autonomous agents that drive PRs to merge should branch
on the JSON ``"merged"`` field rather than the exit code. Callers that want
standard exit semantics (0 for merged-success) can pass
``--exit-zero-on-merged``; the JSON payload is unchanged. See issue #2277.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

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
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035

if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    gh_graphql,
    resolve_repo_params,
)

_QUERY = """\
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      state
      merged
      mergedAt
      mergedBy {
        login
      }
    }
  }
}"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check if a GitHub PR has been merged.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--exit-zero-on-merged",
        action="store_true",
        help=(
            "Return exit code 0 (instead of the 100 sentinel) when the PR is "
            "merged. JSON output is unchanged. Use this for autonomous "
            "autofix agents that treat any nonzero exit as failure."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    try:
        data = gh_graphql(
            _QUERY,
            {"owner": owner, "repo": repo, "prNumber": args.pull_request},
        )
    except RuntimeError as exc:
        error_and_exit(f"GraphQL query failed: {exc}", 3)

    pr = data.get("repository", {}).get("pullRequest")
    if not pr:
        error_and_exit(
            f"PR #{args.pull_request} not found in {owner}/{repo}.", 2,
        )

    merged_by = pr.get("mergedBy", {})
    merged_by_login = merged_by.get("login") if merged_by else None

    output = {
        "success": True,
        "pull_request": args.pull_request,
        "owner": owner,
        "repo": repo,
        "state": pr.get("state"),
        "merged": pr.get("merged", False),
        "merged_at": pr.get("mergedAt"),
        "merged_by": merged_by_login,
    }

    print(json.dumps(output, indent=2))

    if pr.get("merged"):
        return 0 if args.exit_zero_on_merged else 100

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
