#!/usr/bin/env python3
"""Apply labels to a GitHub Issue with auto-creation support.

Manages labels on GitHub Issues:
- Creates labels if they do not exist
- Applies multiple labels to an issue
- Supports priority labels with standard formatting

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    3 = API error (any label failed)
    4 = Not authenticated
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.parse

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
    write_error_and_exit,
)


def set_issue_labels(
    owner: str,
    repo: str,
    issue: int,
    labels: list[str],
    priority: str = "",
    create_missing: bool = True,
    default_color: str = "ededed",
    priority_color: str = "FFA500",
) -> dict:
    """Apply labels to a GitHub issue.

    Args:
        owner: Repository owner.
        repo: Repository name.
        issue: Issue number.
        labels: List of label names.
        priority: Priority level (P0-P3), creates "priority:PX" label.
        create_missing: Create labels that do not exist.
        default_color: Hex color for auto-created labels.
        priority_color: Hex color for priority labels.

    Returns:
        Dict with label application results.
    """
    all_labels = [
        {"name": label.strip(), "color": default_color}
        for label in labels
        if label.strip()
    ]
    if priority.strip():
        all_labels.append({
            "name": f"priority:{priority}",
            "color": priority_color,
        })

    if not all_labels:
        return {
            "Success": True,
            "Issue": issue,
            "Applied": [],
            "Created": [],
            "Failed": [],
            "TotalApplied": 0,
        }

    applied = []
    created = []
    failed = []

    for label_info in all_labels:
        label_name = label_info["name"]
        label_color = label_info["color"]
        encoded_name = urllib.parse.quote(label_name, safe="")

        # Check if label exists
        check = _run_gh(
            "api", f"repos/{owner}/{repo}/labels/{encoded_name}",
            check=False,
        )
        exists = check.returncode == 0

        if not exists:
            if create_missing:
                create_result = subprocess.run(
                    [
                        "gh", "api", f"repos/{owner}/{repo}/labels",
                        "-X", "POST",
                        "-f", f"name={label_name}",
                        "-f", f"color={label_color}",
                        "-f", "description=Auto-created by AI triage",
                    ],
                    capture_output=True,
                    text=True,
                )
                if create_result.returncode == 0:
                    created.append(label_name)
                else:
                    failed.append(label_name)
                    continue
            else:
                continue

        add_result = subprocess.run(
            [
                "gh", "issue", "edit", str(issue),
                "--repo", f"{owner}/{repo}",
                "--add-label", label_name,
            ],
            capture_output=True,
            text=True,
        )
        if add_result.returncode == 0:
            applied.append(label_name)
        else:
            failed.append(label_name)

    return {
        "Success": len(failed) == 0,
        "Issue": issue,
        "Applied": applied,
        "Created": created,
        "Failed": failed,
        "TotalApplied": len(applied),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply labels to a GitHub issue"
    )
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument(
        "--labels", nargs="*", default=[],
        help="Label names to apply",
    )
    parser.add_argument(
        "--priority", default="",
        choices=["", "P0", "P1", "P2", "P3"],
        help="Priority level (creates priority:PX label)",
    )
    parser.add_argument(
        "--no-create-missing", action="store_true",
        help="Do not create labels that do not exist",
    )
    parser.add_argument(
        "--default-color", default="ededed",
        help="Hex color for auto-created labels",
    )
    parser.add_argument(
        "--priority-color", default="FFA500",
        help="Hex color for priority labels",
    )
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    output = set_issue_labels(
        resolved["owner"], resolved["repo"], args.issue,
        args.labels, args.priority,
        create_missing=not args.no_create_missing,
        default_color=args.default_color,
        priority_color=args.priority_color,
    )

    print(json.dumps(output, indent=2))
    if output["Applied"]:
        names = ", ".join(output["Applied"])
        print(
            f"Applied {output['TotalApplied']} label(s) to issue "
            f"#{args.issue}: {names}",
            file=sys.stderr,
        )
    if output["Failed"]:
        names = ", ".join(output["Failed"])
        print(f"Failed: {names}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
