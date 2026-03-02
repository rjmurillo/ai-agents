#!/usr/bin/env python3
"""Add a reaction to one or more GitHub comments.

Adds emoji reactions to PR review comments or issue comments.
Supports batch operations. Common use: eyes to acknowledge
receipt of review comments.

Exit codes (ADR-035):
    0 = All succeeded
    1 = Invalid parameters
    3 = Any failed
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
    _run_gh,
    assert_gh_authenticated,
    resolve_repo_params,
)

REACTION_EMOJI = {
    "+1": "thumbs_up",
    "-1": "thumbs_down",
    "laugh": "laughing",
    "confused": "confused",
    "heart": "heart",
    "hooray": "tada",
    "rocket": "rocket",
    "eyes": "eyes",
}

VALID_REACTIONS = list(REACTION_EMOJI.keys())


def add_comment_reaction(
    owner: str,
    repo: str,
    comment_ids: list[int],
    comment_type: str = "review",
    reaction: str = "eyes",
) -> dict:
    """Add a reaction to one or more GitHub comments.

    Args:
        owner: Repository owner.
        repo: Repository name.
        comment_ids: List of comment IDs to react to.
        comment_type: "review" for PR review comments, "issue" for issue comments.
        reaction: Reaction type (e.g., "+1", "eyes", "heart").

    Returns:
        Dict with batch operation summary.
    """
    succeeded = 0
    failed = 0
    results = []

    for cid in comment_ids:
        if comment_type == "review":
            endpoint = f"repos/{owner}/{repo}/pulls/comments/{cid}/reactions"
        else:
            endpoint = f"repos/{owner}/{repo}/issues/comments/{cid}/reactions"

        result = _run_gh(
            "api", endpoint, "-X", "POST", "-f", f"content={reaction}",
            check=False,
        )

        success = (
            result.returncode == 0
            or "already reacted" in result.stdout
        )

        if success:
            succeeded += 1
            results.append({
                "Success": True,
                "CommentId": cid,
                "CommentType": comment_type,
                "Reaction": reaction,
                "Error": None,
            })
        else:
            failed += 1
            results.append({
                "Success": False,
                "CommentId": cid,
                "CommentType": comment_type,
                "Reaction": reaction,
                "Error": result.stderr or result.stdout,
            })

    return {
        "TotalCount": len(comment_ids),
        "Succeeded": succeeded,
        "Failed": failed,
        "Reaction": reaction,
        "CommentType": comment_type,
        "Results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add a reaction to GitHub comments"
    )
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument(
        "--comment-id", type=int, nargs="+", required=True,
        help="Comment ID(s) to react to",
    )
    parser.add_argument(
        "--comment-type", default="review",
        choices=["review", "issue"],
        help="Comment type",
    )
    parser.add_argument(
        "--reaction", required=True, choices=VALID_REACTIONS,
        help="Reaction type",
    )
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    output = add_comment_reaction(
        resolved["owner"], resolved["repo"],
        args.comment_id, args.comment_type, args.reaction,
    )

    print(json.dumps(output, indent=2))

    total = output["TotalCount"]
    ok = output["Succeeded"]
    if total > 1:
        print(f"Batch complete: {ok}/{total} succeeded", file=sys.stderr)
    elif ok > 0:
        print(
            f"Added {args.reaction} to {args.comment_type} comment "
            f"{args.comment_id[0]}",
            file=sys.stderr,
        )

    if output["Failed"] > 0:
        sys.exit(3)


if __name__ == "__main__":
    main()
