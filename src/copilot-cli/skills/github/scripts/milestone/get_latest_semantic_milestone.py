#!/usr/bin/env python3
"""Detect the latest open semantic version milestone in a GitHub repository.

Queries GitHub API for all open milestones, filters those matching semantic
versioning format (X.Y.Z), sorts by version number, and returns the latest.

Exit codes follow ADR-035:
    0 - Success: Milestone found
    1 - Invalid parameters
    2 - Config or usage error
    3 - External error (API failure, or no open or semantic milestones
        found; Error.Type is NotFound for a missing milestone, ApiError otherwise)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skill_bootstrap import ensure_plugin_paths

ensure_plugin_paths(__file__, (".claude", "lib"))

from github_core import (
    add_output_format_arg,
    assert_gh_authenticated,
    get_output_format,
    gh_api_paginated,
    resolve_repo_params,
    write_github_output,
    write_skill_error,
    write_skill_output,
    write_step_summary,
)

# Optional v prefix matches the repository tag and milestone convention
# (every milestone since 0.3.0 is v-prefixed; see issue #3945).
_SEMVER_PATTERN = re.compile(r"^v?\d+\.\d+\.\d+$")


def _parse_semver_tuple(version: str) -> tuple[int, ...]:
    """Parse 'X.Y.Z' into (X, Y, Z) for proper numeric sorting."""
    return tuple(int(part) for part in version.removeprefix("v").split("."))


_HELP_EPILOG = """\
examples:
  %(prog)s
  %(prog)s --output-format json

exit codes:
  0  success: Milestone found
  2  config or usage error
  3  external error (API failure, or no semantic milestones found; see Error.Type)
  4  auth error (not authenticated)
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect the latest open semantic version milestone.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    endpoint = f"repos/{owner}/{repo}/milestones?state=open"
    milestones = gh_api_paginated(endpoint)

    if not milestones:
        print(f"No open milestones found in {owner}/{repo}", file=sys.stderr)
        write_skill_error(
            f"No open milestones found in {owner}/{repo}",
            3,
            error_type="NotFound",
            output_format=fmt,
            script_name="get_latest_semantic_milestone.py",
            extra={"title": "", "number": 0, "found": False},
        )
        write_github_output(
            {
                "milestone_title": "",
                "milestone_number": "0",
                "found": "false",
            }
        )
        write_step_summary(
            f"## Milestone Detection Result\n\n"
            f"**Status**: No semantic version milestones found\n\n"
            f"No open milestones matching semantic versioning format (X.Y.Z) "
            f"were found in **{owner}/{repo}**.\n\n"
            f"**Action**: Create a semantic version milestone (e.g., 0.2.0, 1.0.0).\n"
        )
        return 3

    semantic = [m for m in milestones if _SEMVER_PATTERN.match(m.get("title", ""))]

    if not semantic:
        available = ", ".join(m.get("title", "(untitled)") for m in milestones)
        print(
            f"No semantic version milestones found. Available: {available}",
            file=sys.stderr,
        )
        write_skill_error(
            f"No semantic version milestones found. Available: {available}",
            3,
            error_type="NotFound",
            output_format=fmt,
            script_name="get_latest_semantic_milestone.py",
            extra={"title": "", "number": 0, "found": False},
        )
        write_github_output(
            {
                "milestone_title": "",
                "milestone_number": "0",
                "found": "false",
            }
        )
        available_list = "\n".join(f"- {m.get('title', '(untitled)')}" for m in milestones)
        write_step_summary(
            f"## Milestone Detection Result\n\n"
            f"**Status**: No semantic version milestones found\n\n"
            f"Found {len(milestones)} open milestone(s), but none match "
            f"semantic versioning format (X.Y.Z):\n\n{available_list}\n\n"
            f"**Action**: Create a semantic version milestone (e.g., 0.2.0, 1.0.0).\n"
        )
        return 3

    latest = max(semantic, key=lambda m: _parse_semver_tuple(m["title"]))

    write_skill_output(
        {
            "title": latest["title"],
            "number": latest["number"],
            "found": True,
        },
        output_format=fmt,
        human_summary=(f"Latest semantic milestone: {latest['title']} (ID: {latest['number']})"),
        script_name="get_latest_semantic_milestone.py",
    )

    write_github_output(
        {
            "milestone_title": latest["title"],
            "milestone_number": str(latest["number"]),
            "found": "true",
        }
    )

    semver_list = "\n".join(f"- **{m['title']}** (ID: {m['number']})" for m in semantic)
    write_step_summary(
        f"## Milestone Detection Result\n\n"
        f"**Status**: Found semantic version milestone\n\n"
        f"**Milestone**: {latest['title']} (ID: {latest['number']})\n\n"
        f"All {len(semantic)} semantic version milestone(s) found:\n{semver_list}\n"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
