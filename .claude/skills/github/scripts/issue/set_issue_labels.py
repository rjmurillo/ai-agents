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
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    resolve_repo_params,
)
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

VALID_PRIORITIES = ("P0", "P1", "P2", "P3")
PRIORITY_PREFIX = "priority:"


def compute_priority_removals(
    existing: list[str], incoming: list[str],
) -> list[str]:
    """Return existing ``priority:*`` labels to remove for mutual exclusivity.

    Issue #2623: an issue must carry at most one ``priority:*`` label. When a
    new priority label is applied, every existing priority label that is not
    the one being set is stale and must be removed. The label being re-stamped
    (same name) is kept so we do not remove-then-re-add it.

    Returns an empty list when ``incoming`` carries no priority label: this
    function never touches priorities the caller did not ask to change.
    """
    incoming_priorities = {
        name for name in incoming if name.lower().startswith(PRIORITY_PREFIX)
    }
    if not incoming_priorities:
        return []
    return [
        name
        for name in existing
        if name.lower().startswith(PRIORITY_PREFIX)
        and name not in incoming_priorities
    ]


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
    add_output_format_arg(parser)
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


def _get_issue_labels(owner: str, repo: str, issue: int) -> list[str]:
    """Return the issue's current label names. Empty list on any gh failure.

    Failing soft (empty list) means a transient gh hiccup degrades to "no
    removals" rather than blocking the label apply: the worst case is a stale
    priority label survives one pass, which the dual-priority validator still
    catches. It never blocks the intended apply.
    """
    result = subprocess.run(
        [
            "gh", "issue", "view", str(issue),
            "--repo", f"{owner}/{repo}",
            "--json", "labels",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    labels_field = payload.get("labels")
    labels = labels_field if isinstance(labels_field, list) else []
    return [
        item.get("name")
        for item in labels
        if isinstance(item, dict) and item.get("name")
    ]


def _remove_label(owner: str, repo: str, issue: int, label_name: str) -> bool:
    """Remove a label from an issue. Returns True on success."""
    result = subprocess.run(
        [
            "gh", "issue", "edit", str(issue),
            "--repo", f"{owner}/{repo}",
            "--remove-label", label_name,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _reconcile_priorities(
    owner: str, repo: str, issue: int, incoming: list[str],
) -> list[str]:
    """Remove existing priority labels that conflict with the incoming set.

    Returns the labels actually removed so the caller can report them. A
    remove that fails is skipped silently: the apply still proceeds, and the
    dual-priority validator catches any survivor.
    """
    existing = _get_issue_labels(owner, repo, issue)
    to_remove = compute_priority_removals(existing, incoming)
    removed: list[str] = []
    for label_name in to_remove:
        if _remove_label(owner, repo, issue, label_name):
            removed.append(label_name)
    return removed


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    fmt = get_output_format(args.output_format)

    create_missing = not args.no_create_missing

    all_labels: list[dict[str, str]] = []
    for label in args.labels:
        stripped = label.strip()
        if stripped:
            all_labels.append({"name": stripped, "color": args.default_color})

    if args.priority:
        all_labels.append({"name": f"priority:{args.priority}", "color": args.priority_color})

    # Enforce priority mutual exclusivity in the incoming set (Issue #2623).
    # If multiple priority labels are specified, keep only the last one.
    # --priority is added last, so it takes precedence over --labels.
    priority_indices = [
        i for i, label_info in enumerate(all_labels)
        if label_info["name"].lower().startswith(PRIORITY_PREFIX)
    ]
    if len(priority_indices) > 1:
        for i in reversed(priority_indices[:-1]):
            all_labels.pop(i)

    if not all_labels:
        print("No labels to apply.", file=sys.stderr)
        return 0

    incoming_names = [label_info["name"] for label_info in all_labels]

    applied: list[str] = []
    created: list[str] = []
    failed: list[str] = []
    removed: list[str] = []

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
            if label_name.lower().startswith(PRIORITY_PREFIX):
                removed = _reconcile_priorities(owner, repo, args.issue, incoming_names)
        else:
            failed.append(label_name)

    data = {
        "issue": args.issue,
        "applied": applied,
        "created": created,
        "removed": removed,
        "failed": failed,
        "total_applied": len(applied),
    }

    if failed:
        write_skill_error(
            f"Failed: {', '.join(failed)}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="set_issue_labels.py",
            extra=data,
        )
        raise SystemExit(3)

    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"Applied {len(applied)} label(s) to issue #{args.issue}",
        status="PASS",
        script_name="set_issue_labels.py",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
