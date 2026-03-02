#!/usr/bin/env python3
"""Add a reaction to one or more GitHub comments.

Supports batch operations for improved performance.
Common use: eyes to acknowledge receipt of review comments.

Exit codes follow ADR-035:
    0 - All succeeded
    1 - Invalid parameters / logic error
    3 - Any failed
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    resolve_repo_params,
)

REACTION_EMOJI: dict[str, str] = {
    "+1": "\U0001f44d",
    "-1": "\U0001f44e",
    "laugh": "\U0001f604",
    "confused": "\U0001f615",
    "heart": "\u2764\ufe0f",
    "hooray": "\U0001f389",
    "rocket": "\U0001f680",
    "eyes": "\U0001f440",
}

VALID_REACTIONS = list(REACTION_EMOJI.keys())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add a reaction to one or more GitHub comments.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--comment-id",
        nargs="+",
        type=int,
        required=True,
        help="One or more comment IDs to react to",
    )
    parser.add_argument(
        "--comment-type",
        choices=["review", "issue"],
        default="review",
        help='Comment type: "review" for PR review comments, "issue" for issue comments',
    )
    parser.add_argument(
        "--reaction",
        required=True,
        choices=VALID_REACTIONS,
        help="Reaction type",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    emoji = REACTION_EMOJI.get(args.reaction, args.reaction)
    succeeded = 0
    failed = 0
    results: list[dict] = []

    for cid in args.comment_id:
        if args.comment_type == "review":
            endpoint = f"repos/{owner}/{repo}/pulls/comments/{cid}/reactions"
        else:
            endpoint = f"repos/{owner}/{repo}/issues/comments/{cid}/reactions"

        result = subprocess.run(
            ["gh", "api", endpoint, "-X", "POST", "-f", f"content={args.reaction}"],
            capture_output=True, text=True, check=False,
        )

        # Duplicate reactions are OK (idempotent)
        success = result.returncode == 0 or "already reacted" in (result.stderr + result.stdout)

        if success:
            succeeded += 1
            results.append({
                "success": True,
                "comment_id": cid,
                "comment_type": args.comment_type,
                "reaction": args.reaction,
                "emoji": emoji,
                "error": None,
            })
        else:
            failed += 1
            error_str = result.stderr.strip() or result.stdout.strip()
            results.append({
                "success": False,
                "comment_id": cid,
                "comment_type": args.comment_type,
                "reaction": args.reaction,
                "emoji": emoji,
                "error": error_str,
            })

    summary = {
        "total_count": len(args.comment_id),
        "succeeded": succeeded,
        "failed": failed,
        "reaction": args.reaction,
        "emoji": emoji,
        "comment_type": args.comment_type,
        "results": results,
    }

    print(json.dumps(summary, indent=2))

    if failed > 0:
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
