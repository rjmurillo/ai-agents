#!/usr/bin/env python3
"""Check if a GitHub Pull Request has been merged.

Queries GitHub GraphQL API to determine PR merge state.
Use this before starting PR review work to prevent wasted effort on merged PRs.
Per Skill-PR-Review-007: gh pr view may return stale data.

Exit codes follow ADR-035:
    0   - Query succeeded; merge state reported in JSON ``"merged"`` field
    2   - Config error, or the remote answered "no such PR"
    3   - External error (API failure, timeout, unusable payload)
    4   - Auth error
    100 - Legacy skip-review sentinel, only with ``--exit-100-on-merged``

The script exits 0 on a successful query regardless of merge state. Callers
should branch on the JSON ``"merged"`` field. This makes the script behave
like every other shell-friendly probe ("exit 0 means I answered your
question") and stops a successful merge verification from looking like a
failed call. See issue #2308.

The merge state comes from ``github_core.pr_merge_state.read_pr_merge_state``,
which owns the GraphQL query this script used to hold itself. One reader means
this script and ``close_issue.py --verify-claims`` cannot drift into
disagreeing about whether a PR is merged, which is the failure issue #4951
recorded: on 2026-08-13 the REST probe in ``close_issue.py`` called PR #4729
and PR #3076 unmerged and this script proved both merged.

Two behaviors changed with that move (issue #4951):

- An auth failure during the query now exits 4 instead of 3. The table above
  always documented 4 as the auth code; previously only the ``gh auth status``
  preflight could produce it.
- A payload with no boolean ``merged`` field now exits 3 instead of printing
  ``"merged": false``. A missing field is missing evidence, not a No.

The legacy exit-100 sentinel from Skill-PR-Review-007 remains available via
``--exit-100-on-merged`` for scripts that already encoded the "100 = skip
review" convention. The opposite-named flag ``--exit-zero-on-merged`` from
issue #2277 still parses (as a no-op) for backward compatibility.
"""

from __future__ import annotations

import argparse
import json
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
    error_and_exit,
    resolve_repo_params,
)
from github_core.pr_merge_state import PrMergeStatus, read_pr_merge_state


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
            "Deprecated no-op (issue #2308 made exit 0 the default for merged "
            "PRs). Kept for backward compatibility with callers that already "
            "pass this flag. Use --exit-100-on-merged to restore the legacy "
            "sentinel."
        ),
    )
    parser.add_argument(
        "--exit-100-on-merged",
        action="store_true",
        help=(
            "Restore the legacy Skill-PR-Review-007 skip-review sentinel: "
            "return exit code 100 (instead of 0) when the PR is merged. JSON "
            "output is unchanged. Use this only for scripts that already "
            "branch on the 100 sentinel."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    state = read_pr_merge_state(owner, repo, args.pull_request)

    if state.status is PrMergeStatus.PROBE_FAILED:
        error_and_exit(f"GraphQL query failed: {state.detail}", state.exit_code)
    if state.status is PrMergeStatus.NOT_FOUND:
        error_and_exit(
            f"PR #{args.pull_request} not found in {owner}/{repo}.", 2,
        )

    output = {
        "success": True,
        "pull_request": args.pull_request,
        "owner": owner,
        "repo": repo,
        "state": state.state,
        "merged": state.is_merged,
        "merged_at": state.merged_at,
        "merged_by": state.merged_by,
    }

    print(json.dumps(output, indent=2))

    if state.is_merged:
        return 100 if args.exit_100_on_merged else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
