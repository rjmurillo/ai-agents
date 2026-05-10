#!/usr/bin/env python3
"""Edit a GitHub Issue body.

Reads body content from --body or --body-file and replaces the issue body
via `gh issue edit`. Used to keep issue body text in sync with shipped
spec/implementation when the spec or design changes during a PR.

Exit codes (per ADR-035):
    0 - Success
    1 - Invalid parameters / logic error
    2 - Config/environment error (missing lib dir, body-file not found,
        path-traversal rejected, gh CLI binary missing, gh CLI timeout)
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

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
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import error_and_exit, resolve_repo_params  # noqa: E402
from github_core.validation import assert_valid_body_file  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Edit a GitHub Issue body. Replaces the entire body."
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--issue", required=True, type=int, help="Issue number to edit"
    )
    parser.add_argument(
        "--body",
        default=None,
        help="New body text (mutually exclusive with --body-file)",
    )
    parser.add_argument(
        "--body-file",
        default=None,
        help="Path to file containing new body text",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.body is None and args.body_file is None:
        error_and_exit("Must provide --body or --body-file", 1)
    if args.body is not None and args.body_file is not None:
        error_and_exit("--body and --body-file are mutually exclusive", 1)

    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    if args.body_file:
        # CWE-22 path traversal hardening: assert_valid_body_file rejects
        # symlinks and paths outside the repo root. Matches other GitHub
        # skill scripts (PR #1965 copilot review cluster I).
        assert_valid_body_file(args.body_file)
        body = Path(args.body_file).read_text(encoding="utf-8")
    else:
        body = args.body

    gh_args = [
        "gh",
        "issue",
        "edit",
        str(args.issue),
        "--repo",
        f"{owner}/{repo}",
        "--body",
        body,
    ]

    try:
        result = subprocess.run(
            gh_args, capture_output=True, text=True, check=False, timeout=30
        )
    except FileNotFoundError:
        # gh CLI binary missing: environment failure per ADR-035 exit 2.
        # PR #1965 cluster Q.
        error_and_exit("gh CLI not found on PATH", 2)
    except subprocess.TimeoutExpired:
        # gh hung past timeout: environment failure (network, rate limit,
        # auth prompt). Treat as config/env per ADR-035. PR #1965 cluster Q.
        error_and_exit("gh issue edit timed out after 30s", 2)

    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        if "authentication" in error_str.lower() or "not logged in" in error_str.lower():
            error_and_exit(f"Auth error: {error_str}", 4)
        error_and_exit(f"Failed to edit issue: {error_str}", 3)

    # Emit structured JSON to match sibling scripts (new_issue.py,
    # post_issue_comment.py). PR #1965 cluster R.
    print(
        json.dumps(
            {
                "issue": args.issue,
                "status": "updated",
                "repo": f"{owner}/{repo}",
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
