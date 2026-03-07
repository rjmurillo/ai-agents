#!/usr/bin/env python3
"""Assign a milestone to a GitHub Issue.

Validates milestone exists before assigning, and optionally clears existing milestone.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Milestone not found
    3 - External error (API failure)
    4 - Auth error (not authenticated)
    5 - Has milestone (use --force)
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
    error_and_exit,
    resolve_repo_params,
)


def _write_github_output(outputs: dict[str, str]) -> None:
    """Write key=value pairs to GITHUB_OUTPUT if available."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        return
    try:
        with open(output_file, "a", encoding="utf-8") as fh:
            for key, value in outputs.items():
                fh.write(f"{key}={value}\n")
    except OSError:
        pass


def _get_current_milestone(owner: str, repo: str, issue: int) -> str | None:
    """Get the current milestone title for an issue, or None."""
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/issues/{issue}", "--jq", ".milestone.title"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    title = result.stdout.strip()
    if not title or title == "null":
        return None
    return title


def _get_milestone_titles(owner: str, repo: str) -> list[str]:
    """Get all milestone titles from the repository."""
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/milestones", "--jq", ".[].title"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [t.strip() for t in result.stdout.strip().splitlines() if t.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assign a milestone to a GitHub Issue.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument("--milestone", default="", help="Milestone title to assign")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Remove existing milestone",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing milestone",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    if not args.clear and not args.milestone:
        error_and_exit("Must specify --milestone or --clear.", 2)

    current_milestone = _get_current_milestone(owner, repo, args.issue)

    output = {
        "success": False,
        "issue": args.issue,
        "milestone": None,
        "previous_milestone": current_milestone,
        "action": "none",
    }

    if args.clear:
        if not current_milestone:
            output["success"] = True
            output["action"] = "no_change"
            print(json.dumps(output, indent=2))
            _write_github_output({
                "success": "true",
                "issue": str(args.issue),
                "action": "no_change",
            })
            return 0

        result = subprocess.run(
            [
                "gh", "api",
                f"repos/{owner}/{repo}/issues/{args.issue}",
                "-X", "PATCH", "-f", "milestone=",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            error_and_exit("Failed to clear milestone", 3)

        output["success"] = True
        output["action"] = "cleared"
        print(json.dumps(output, indent=2))
        _write_github_output({
            "success": "true",
            "issue": str(args.issue),
            "action": "cleared",
            "previous_milestone": current_milestone,
        })
        return 0

    milestone_titles = _get_milestone_titles(owner, repo)
    if args.milestone not in milestone_titles:
        error_and_exit(
            f"Milestone '{args.milestone}' does not exist in {owner}/{repo}.",
            2,
        )

    if current_milestone == args.milestone:
        output["success"] = True
        output["milestone"] = args.milestone
        output["action"] = "no_change"
        print(json.dumps(output, indent=2))
        _write_github_output({
            "success": "true",
            "issue": str(args.issue),
            "milestone": args.milestone,
            "action": "no_change",
        })
        return 0

    if current_milestone and not args.force:
        error_and_exit(
            f"Issue #{args.issue} already has milestone "
            f"'{current_milestone}'. Use --force to override.",
            5,
        )

    result = subprocess.run(
        [
            "gh", "issue", "edit", str(args.issue),
            "--repo", f"{owner}/{repo}",
            "--milestone", args.milestone,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        error_and_exit("Failed to set milestone", 3)

    action = "replaced" if current_milestone else "assigned"
    output["success"] = True
    output["milestone"] = args.milestone
    output["action"] = action
    print(json.dumps(output, indent=2))

    gh_outputs: dict[str, str] = {
        "success": "true",
        "issue": str(args.issue),
        "milestone": args.milestone,
        "action": action,
    }
    if current_milestone:
        gh_outputs["previous_milestone"] = current_milestone
    _write_github_output(gh_outputs)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
