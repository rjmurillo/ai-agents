#!/usr/bin/env python3
"""Detect the latest open semantic version milestone in a GitHub repository.

Queries GitHub API for all open milestones, filters those matching semantic
versioning format (X.Y.Z), sorts by version number, and returns the latest.

Exit codes follow ADR-035:
    0 - Success: Milestone found
    1 - Invalid parameters
    2 - Config/resource error (no semantic milestones found)
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
    gh_api_paginated,
    resolve_repo_params,
)

_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def _parse_semver_tuple(version: str) -> tuple[int, ...]:
    """Parse 'X.Y.Z' into (X, Y, Z) for proper numeric sorting."""
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect the latest open semantic version milestone.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    endpoint = f"repos/{owner}/{repo}/milestones?state=open"
    milestones = gh_api_paginated(endpoint)

    if not milestones:
        print(f"No open milestones found in {owner}/{repo}", file=sys.stderr)
        result = {"title": "", "number": 0, "found": False}
        print(json.dumps(result, indent=2))
        _write_github_output({
            "milestone_title": "",
            "milestone_number": "0",
            "found": "false",
        })
        _write_step_summary(
            f"## Milestone Detection Result\n\n"
            f"**Status**: No semantic version milestones found\n\n"
            f"No open milestones matching semantic versioning format (X.Y.Z) "
            f"were found in **{owner}/{repo}**.\n\n"
            f"**Action**: Create a semantic version milestone (e.g., 0.2.0, 1.0.0).\n"
        )
        return 2

    semantic = [m for m in milestones if _SEMVER_PATTERN.match(m.get("title", ""))]

    if not semantic:
        available = ", ".join(m.get("title", "(untitled)") for m in milestones)
        print(
            f"No semantic version milestones found. Available: {available}",
            file=sys.stderr,
        )
        result = {"title": "", "number": 0, "found": False}
        print(json.dumps(result, indent=2))
        _write_github_output({
            "milestone_title": "",
            "milestone_number": "0",
            "found": "false",
        })
        available_list = "\n".join(f"- {m.get('title', '(untitled)')}" for m in milestones)
        _write_step_summary(
            f"## Milestone Detection Result\n\n"
            f"**Status**: No semantic version milestones found\n\n"
            f"Found {len(milestones)} open milestone(s), but none match "
            f"semantic versioning format (X.Y.Z):\n\n{available_list}\n\n"
            f"**Action**: Create a semantic version milestone (e.g., 0.2.0, 1.0.0).\n"
        )
        return 2

    latest = max(semantic, key=lambda m: _parse_semver_tuple(m["title"]))

    result = {
        "title": latest["title"],
        "number": latest["number"],
        "found": True,
    }
    print(json.dumps(result, indent=2))

    _write_github_output({
        "milestone_title": latest["title"],
        "milestone_number": str(latest["number"]),
        "found": "true",
    })

    semver_list = "\n".join(
        f"- **{m['title']}** (ID: {m['number']})" for m in semantic
    )
    _write_step_summary(
        f"## Milestone Detection Result\n\n"
        f"**Status**: Found semantic version milestone\n\n"
        f"**Milestone**: {latest['title']} (ID: {latest['number']})\n\n"
        f"All {len(semantic)} semantic version milestone(s) found:\n{semver_list}\n"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
