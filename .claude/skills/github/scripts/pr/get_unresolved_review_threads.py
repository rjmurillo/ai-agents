#!/usr/bin/env python3
"""Get unresolved review threads for a GitHub Pull Request.

Thin wrapper around the get_unresolved_review_threads helper in github_core.api.
Uses GitHub GraphQL API to query review thread resolution status.

Part of the "Acknowledged vs Resolved" lifecycle model:
NEW -> ACKNOWLEDGED (eyes reaction) -> REPLIED -> RESOLVED (thread marked resolved)

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    3 - External error (API failure)
    4 - Auth error
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
    _lib_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib"))
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    get_unresolved_review_threads,
    resolve_repo_params,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get unresolved review threads for a GitHub PR.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.pull_request <= 0:
        error_and_exit("Pull request number must be positive.", 1)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["Owner"], resolved["Repo"]

    threads = get_unresolved_review_threads(owner, repo, args.pull_request)
    print(json.dumps(threads, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
