#!/usr/bin/env python3
"""Get unresolved review threads for a GitHub Pull Request.

Thin wrapper that queries GraphQL for unresolved review threads.
Returns threads where isResolved = false.

Exit codes (ADR-035):
    0 = Success
    2 = Not found
    3 = API error
    4 = Not authenticated
"""

import argparse
import json
import os
import sys

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    gh_graphql,
    resolve_repo_params,
    write_error_and_exit,
)

QUERY = """
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes {
              databaseId
              author { login }
              body
            }
          }
        }
      }
    }
  }
}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Get unresolved PR review threads")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    try:
        data = gh_graphql(QUERY, {
            "owner": resolved["owner"],
            "repo": resolved["repo"],
            "prNumber": args.pull_request,
        })
    except Exception as e:
        write_error_and_exit(f"Failed to query review threads: {e}", 3)

    pr_data = data.get("repository", {}).get("pullRequest")
    if not pr_data:
        write_error_and_exit(f"PR #{args.pull_request} not found", 2)

    all_threads = pr_data.get("reviewThreads", {}).get("nodes", [])
    unresolved = [t for t in all_threads if not t.get("isResolved", False)]

    print(json.dumps(unresolved, indent=2))


if __name__ == "__main__":
    main()
