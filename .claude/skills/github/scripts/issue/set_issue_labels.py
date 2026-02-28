#!/usr/bin/env python3
"""Apply labels to a GitHub Issue with auto-creation support.

Creates labels if they don't exist, applies multiple labels to an issue,
and supports priority labels with standard formatting.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from urllib.parse import quote

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

VALID_PRIORITIES = ("P0", "P1", "P2", "P3")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply labels to a GitHub Issue with auto-creation support.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument(
        "--labels",
        nargs="*",
        default=[],
        help="Label names to apply",
    )
    parser.add_argument(
        "--priority",
        default="",
        choices=["", *VALID_PRIORITIES],
        help="Priority level (P0, P1, P2, P3). Creates 'priority:PX' label.",
    )
    parser.add_argument(
        "--no-create-missing",
        action="store_true",
        help="Do not auto-create labels that don't exist",
    )
    parser.add_argument(
        "--default-color",
        default="ededed",
        help="Default color for auto-created labels",
    )
    parser.add_argument(
        "--priority-color",
        default="FFA500",
        help="Color for priority labels",
    )
    return parser


def _label_exists(owner: str, repo: str, label_name: str) -> bool:
    """Check if a label exists in the repository."""
    encoded = quote(label_name, safe="")
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/labels/{encoded}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _create_label(
    owner: str, repo: str, label_name: str, color: str,
) -> bool:
    """Create a label in the repository. Returns True on success."""
    result = subprocess.run(
        [
            "gh", "api", f"repos/{owner}/{repo}/labels",
            "-X", "POST",
            "-f", f"name={label_name}",
            "-f", f"color={color}",
            "-f", "description=Auto-created by AI triage",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _apply_label(owner: str, repo: str, issue: int, label_name: str) -> bool:
    """Apply a label to an issue. Returns True on success."""
    result = subprocess.run(
        [
            "gh", "issue", "edit", str(issue),
            "--repo", f"{owner}/{repo}",
            "--add-label", label_name,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    create_missing = not args.no_create_missing

    all_labels: list[dict[str, str]] = []
    for label in args.labels:
        stripped = label.strip()
        if stripped:
            all_labels.append({"name": stripped, "color": args.default_color})

    if args.priority:
        all_labels.append({"name": f"priority:{args.priority}", "color": args.priority_color})

    if not all_labels:
        print("No labels to apply.", file=sys.stderr)
        return 0

    applied: list[str] = []
    created: list[str] = []
    failed: list[str] = []

    for label_info in all_labels:
        label_name = label_info["name"]
        label_color = label_info["color"]

        exists = _label_exists(owner, repo, label_name)

        if not exists:
            if create_missing:
                if _create_label(owner, repo, label_name, label_color):
                    created.append(label_name)
                else:
                    failed.append(label_name)
                    continue
            else:
                continue

        if _apply_label(owner, repo, args.issue, label_name):
            applied.append(label_name)
        else:
            failed.append(label_name)

    output = {
        "success": len(failed) == 0,
        "issue": args.issue,
        "applied": applied,
        "created": created,
        "failed": failed,
        "total_applied": len(applied),
    }

    print(json.dumps(output, indent=2))

    if failed:
        error_and_exit(f"Failed: {', '.join(failed)}", 3)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
