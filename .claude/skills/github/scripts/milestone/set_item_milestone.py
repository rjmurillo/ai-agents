#!/usr/bin/env python3
"""Assign a milestone to a PR or issue if none exists.

Orchestrates milestone assignment:
1. Checks if item already has a milestone (skips if present)
2. Auto-detects latest semantic version milestone (unless --milestone-title provided)
3. Assigns the milestone

Exit codes follow ADR-035:
    0 - Success (assigned or skipped)
    2 - Config error (no milestone found, detection failed)
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

_WORKSPACE = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
    ),
)
sys.path.insert(0, _WORKSPACE)

from scripts.github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    gh_api_paginated,
    resolve_repo_params,
)

_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def _parse_semver_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


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


def _write_step_summary(content: str) -> None:
    """Write content to GITHUB_STEP_SUMMARY if available."""
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        return
    try:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(content)
    except OSError:
        pass


def _write_result(
    success: bool,
    item_type: str,
    item_number: int,
    milestone: str,
    action: str,
    message: str,
) -> None:
    """Write result to GITHUB_OUTPUT and GITHUB_STEP_SUMMARY."""
    _write_github_output({
        "success": str(success).lower(),
        "item_type": item_type,
        "item_number": str(item_number),
        "milestone": milestone,
        "action": action,
        "message": message,
    })

    icon = "+" if success else "X"
    item_label = "Pull Request" if item_type == "pr" else "Issue"
    _write_step_summary(
        f"## Milestone Assignment Result\n\n"
        f"**Status**: {icon} {action.upper()}\n\n"
        f"**{item_label}**: #{item_number}\n"
        f"**Milestone**: {milestone}\n\n"
        f"{message}\n"
    )


def _get_item_milestone(owner: str, repo: str, number: int) -> str | None:
    """Return the current milestone title for a PR/issue, or None."""
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/issues/{number}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        error_and_exit(f"Failed to query item #{number}: {error_str}", 3)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        error_and_exit(f"Invalid JSON from item #{number}: {exc}", 3)

    milestone = data.get("milestone")
    if milestone and milestone.get("title"):
        return str(milestone["title"])
    return None


def _get_latest_semantic_milestone(owner: str, repo: str) -> dict:
    """Detect the latest open semantic version milestone."""
    endpoint = f"repos/{owner}/{repo}/milestones?state=open"
    milestones = gh_api_paginated(endpoint)

    if not milestones:
        return {"title": "", "number": 0, "found": False}

    semantic = [m for m in milestones if _SEMVER_PATTERN.match(m.get("title", ""))]
    if not semantic:
        available = ", ".join(m.get("title", "(untitled)") for m in milestones)
        print(f"No semantic version milestones found. Available: {available}", file=sys.stderr)
        return {"title": "", "number": 0, "found": False}

    latest = max(semantic, key=lambda m: _parse_semver_tuple(m["title"]))
    return {"title": latest["title"], "number": latest["number"], "found": True}


def _assign_milestone(owner: str, repo: str, number: int, milestone_title: str) -> None:
    """Assign a milestone to a PR/issue via gh CLI."""
    result = subprocess.run(
        [
            "gh", "issue", "edit", str(number),
            "--repo", f"{owner}/{repo}",
            "--milestone", milestone_title,
        ],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        error_and_exit(
            f"Failed to assign milestone '{milestone_title}' to #{number}: {error_str}",
            3,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assign a milestone to a PR or issue if none exists.",
    )
    parser.add_argument(
        "--item-type",
        required=True,
        choices=["pr", "issue"],
        help="Type of item: pr or issue",
    )
    parser.add_argument("--item-number", type=int, required=True, help="PR or issue number")
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--milestone-title",
        default="",
        help="Specific milestone to assign (auto-detects if omitted)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    item_type: str = args.item_type
    item_number: int = args.item_number

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["Owner"], resolved["Repo"]

    # Check current milestone
    existing = _get_item_milestone(owner, repo, item_number)
    if existing:
        msg = (
            f"Already has milestone '{existing}'. "
            "No action taken (preserving manual assignments)."
        )
        print(f"{item_type} #{item_number} already has milestone: {existing}")
        result = {
            "success": True,
            "item_type": item_type,
            "item_number": item_number,
            "milestone": existing,
            "action": "skipped",
            "message": msg,
        }
        print(json.dumps(result, indent=2))
        _write_result(True, item_type, item_number, existing, "skipped", msg)
        return 0

    # Determine milestone to assign
    milestone_title: str = args.milestone_title
    if not milestone_title:
        detection = _get_latest_semantic_milestone(owner, repo)
        if not detection["found"]:
            msg = (
                "No semantic version milestone found. "
                "Create one (e.g., 0.3.0) or pass --milestone-title."
            )
            print(msg, file=sys.stderr)
            _write_result(False, item_type, item_number, "", "failed", msg)
            return 2
        milestone_title = str(detection["title"])

    # Assign
    print(f"Assigning milestone '{milestone_title}' to {item_type} #{item_number}")
    _assign_milestone(owner, repo, item_number, milestone_title)

    msg = f"Assigned milestone '{milestone_title}'."
    print(f"Successfully assigned milestone '{milestone_title}' to {item_type} #{item_number}")
    result = {
        "success": True,
        "item_type": item_type,
        "item_number": item_number,
        "milestone": milestone_title,
        "action": "assigned",
        "message": msg,
    }
    print(json.dumps(result, indent=2))
    _write_result(True, item_type, item_number, milestone_title, "assigned", msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
