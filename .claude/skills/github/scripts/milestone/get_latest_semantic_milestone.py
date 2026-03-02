#!/usr/bin/env python3
"""Detect the latest open semantic version milestone in a GitHub repository.

Queries GitHub API for all open milestones, filters those matching
semantic versioning format (X.Y.Z), sorts by version number using
proper version comparison, and returns the latest milestone details.

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    2 = No semantic milestones found
    3 = API error
    4 = Not authenticated
"""

import argparse
import json
import os
import re
import sys

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    gh_api_paginated,
    resolve_repo_params,
    write_error_and_exit,
)

SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def _parse_version(title: str) -> tuple[int, ...]:
    """Parse a semver string into a comparable tuple."""
    return tuple(int(x) for x in title.split("."))


def get_latest_semantic_milestone(owner: str, repo: str) -> dict:
    """Find the latest semantic version milestone.

    Args:
        owner: Repository owner.
        repo: Repository name.

    Returns:
        Dict with Title, Number, Found keys.
    """
    milestones = gh_api_paginated(
        f"repos/{owner}/{repo}/milestones?state=open"
    )

    if not milestones:
        return {"Title": "", "Number": 0, "Found": False}

    semantic = [
        m for m in milestones
        if SEMVER_PATTERN.match(m.get("title", ""))
    ]

    if not semantic:
        return {"Title": "", "Number": 0, "Found": False}

    latest = max(semantic, key=lambda m: _parse_version(m["title"]))

    return {
        "Title": latest["title"],
        "Number": latest["number"],
        "Found": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Get latest semantic version milestone"
    )
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    output = get_latest_semantic_milestone(
        resolved["owner"], resolved["repo"]
    )

    print(json.dumps(output, indent=2))

    if output["Found"]:
        print(
            f"Latest milestone: {output['Title']} "
            f"(number: {output['Number']})",
            file=sys.stderr,
        )
    else:
        print("No semantic version milestones found", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
