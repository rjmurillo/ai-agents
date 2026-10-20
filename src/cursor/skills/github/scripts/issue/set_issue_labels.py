#!/usr/bin/env python3
"""Apply or remove labels on a GitHub Issue or PR with auto-creation support.

Creates labels if they don't exist, applies multiple labels to an issue,
and supports priority labels with standard formatting. ``--remove-labels``
removes labels (issue #6808); a label the issue does not carry is a no-op.
GitHub labels PRs through the issues API, so a PR number works too.

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

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
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

from github_core.api import (
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

VALID_PRIORITIES = ("P0", "P1", "P2", "P3")
PRIORITY_PREFIX = "priority:"
GH_TIMEOUT_SECONDS = 15


def compute_priority_removals(
    existing: list[str],
    incoming: list[str],
) -> list[str]:
    """Return existing ``priority:*`` labels to remove for mutual exclusivity.

    Issue #2623: an issue must carry at most one ``priority:*`` label. When a
    new priority label is applied, every existing priority label that is not
    the one being set is stale and must be removed. The label being re-stamped
    (same name) is kept so we do not remove-then-re-add it.

    Returns an empty list when ``incoming`` carries no priority label: this
    function never touches priorities the caller did not ask to change.
    """
    incoming_priorities_lower = {
        name.lower() for name in incoming if name.lower().startswith(PRIORITY_PREFIX)
    }
    if not incoming_priorities_lower:
        return []
    return [
        name
        for name in existing
        if name.lower().startswith(PRIORITY_PREFIX)
        and name.lower() not in incoming_priorities_lower
    ]


def expand_labels(raw_labels: list[object]) -> list[str]:
    """Flatten ``--labels`` arguments into individual label names (issue #4967).

    Accepts both public forms so the documented comma syntax and the historical
    space syntax agree:

    - Space-separated arguments from ``nargs="*"``: ``--labels bug enhancement``.
    - Comma-separated values inside any argument: ``--labels "bug,enhancement"``.
    - Repeated ``--labels`` flags (``action="append"`` yields nested lists),
      which accumulate instead of silently dropping earlier groups.

    Commas act as separators, so a label may not contain a literal comma. A
    single argument may still contain spaces, so multi-word names such as
    ``needs discussion`` survive intact. Whitespace around each name is trimmed
    and empty results are dropped.
    """
    names: list[str] = []
    for group in raw_labels:
        tokens = group if isinstance(group, list) else [group]
        for token in tokens:
            if not isinstance(token, str):
                continue
            for part in token.split(","):
                stripped = part.strip()
                if stripped:
                    names.append(stripped)
    return names


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply or remove labels on a GitHub Issue or PR (auto-creates missing labels).",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument(
        "--labels",
        nargs="*",
        action="append",
        default=None,
        help=(
            "Label names to apply. To apply two labels 'bug' and "
            "'enhancement', use either unquoted space-separated arguments "
            "(--labels bug enhancement) or a quoted comma-separated string "
            '(--labels "bug,enhancement"). Only commas split names, so a '
            'quoted space-separated string (--labels "bug enhancement") is '
            "one label named 'bug enhancement'. Repeat the flag to add more; "
            "surrounding whitespace on each name is trimmed."
        ),
    )
    parser.add_argument(
        "--remove-labels",
        nargs="*",
        action="append",
        default=None,
        help=(
            "Label names to remove, with the same comma/space/repeat syntax "
            "as --labels. A label the issue does not carry is skipped with a "
            "note. Removal runs after any additions. A name may not appear in "
            "both --labels and --remove-labels."
        ),
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
        encoding="utf-8",
        errors="replace",
        timeout=GH_TIMEOUT_SECONDS,
        check=False,
    )
    return result.returncode == 0


def _create_label(
    owner: str,
    repo: str,
    label_name: str,
    color: str,
) -> bool:
    """Create a label in the repository. Returns True on success."""
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/labels",
            "-X",
            "POST",
            "-f",
            f"name={label_name}",
            "-f",
            f"color={color}",
            "-f",
            "description=Auto-created by AI triage",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=GH_TIMEOUT_SECONDS,
        check=False,
    )
    return result.returncode == 0


def _apply_label(owner: str, repo: str, issue: int, label_name: str) -> bool:
    """Apply a label to an issue. Returns True on success."""
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "edit",
                str(issue),
                "--repo",
                f"{owner}/{repo}",
                "--add-label",
                label_name,
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def _fetch_issue_labels_strict(owner: str, repo: str, issue: int) -> list[str] | None:
    """Return the issue's label names, or None when the lookup fails.

    Unlike ``_get_issue_labels`` this does not fail soft: an explicit removal
    must tell a missing issue apart from a label the issue does not carry.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                str(issue),
                "--repo",
                f"{owner}/{repo}",
                "--json",
                "labels",
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    labels = payload.get("labels") if isinstance(payload, dict) else None
    if not isinstance(labels, list):
        return None
    return [
        name
        for item in labels
        if isinstance(item, dict) and isinstance(name := item.get("name"), str) and name
    ]


def _get_issue_labels(owner: str, repo: str, issue: int) -> list[str]:
    """Return the issue's current label names. Empty list on any gh failure.

    Failing soft (empty list) means a transient gh hiccup degrades to "no
    removals" rather than blocking the label apply: the worst case is a stale
    priority label survives one pass, which the dual-priority validator still
    catches. It never blocks the intended apply.
    """
    return _fetch_issue_labels_strict(owner, repo, issue) or []


def _remove_label(owner: str, repo: str, issue: int, label_name: str) -> bool:
    """Remove a label from an issue. Returns True on success."""
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "edit",
                str(issue),
                "--repo",
                f"{owner}/{repo}",
                "--remove-label",
                label_name,
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def _reconcile_priorities(
    owner: str,
    repo: str,
    issue: int,
    incoming: list[str],
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
    for name in expand_labels(args.labels or []):
        all_labels.append({"name": name, "color": args.default_color})

    if args.priority:
        all_labels.append({"name": f"priority:{args.priority}", "color": args.priority_color})

    # Enforce priority mutual exclusivity in the incoming set (Issue #2623).
    # If multiple priority labels are specified, keep only the last one.
    # --priority is added last, so it takes precedence over --labels.
    priority_indices = [
        i
        for i, label_info in enumerate(all_labels)
        if label_info["name"].lower().startswith(PRIORITY_PREFIX)
    ]
    if len(priority_indices) > 1:
        for i in reversed(priority_indices[:-1]):
            all_labels.pop(i)

    remove_names = expand_labels(args.remove_labels or [])

    if not all_labels and not remove_names:
        print("No labels to apply.", file=sys.stderr)
        return 0

    conflict = sorted(
        {n.lower() for n in remove_names} & {info["name"].lower() for info in all_labels}
    )
    if conflict:
        write_skill_error(
            f"Label(s) in both add and remove: {', '.join(conflict)}",
            1,
            error_type="InvalidParams",
            output_format=fmt,
            script_name="set_issue_labels.py",
        )
        raise SystemExit(1)

    current_labels: list[str] = []
    if remove_names:
        fetched = _fetch_issue_labels_strict(owner, repo, args.issue)
        if fetched is None:
            write_skill_error(
                f"Could not read labels for #{args.issue} (not found or API failure)",
                3,
                error_type="ApiError",
                output_format=fmt,
                script_name="set_issue_labels.py",
            )
            raise SystemExit(3)
        current_labels = fetched

    incoming_names = [label_info["name"] for label_info in all_labels]

    applied: list[str] = []
    created: list[str] = []
    failed: list[str] = []
    removed: list[str] = []
    removed_requested: list[str] = []
    absent: list[str] = []

    try:
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

        present_lower = {name.lower(): name for name in current_labels}
        for label_name in remove_names:
            actual = present_lower.get(label_name.lower())
            if actual is not None and actual.lower() in {r.lower() for r in removed}:
                continue  # already removed by priority reconciliation
            if actual is None:
                absent.append(label_name)
                print(f"Label '{label_name}' not on #{args.issue}; skipped.", file=sys.stderr)
            elif _remove_label(owner, repo, args.issue, actual):
                removed_requested.append(actual)
            else:
                failed.append(label_name)
    except subprocess.TimeoutExpired as err:
        data = {
            "issue": args.issue,
            "applied": applied,
            "created": created,
            "removed": removed + removed_requested,
            "absent": absent,
            "failed": failed,
            "total_applied": len(applied),
        }
        write_skill_error(
            f"GitHub label operation timed out after {GH_TIMEOUT_SECONDS}s",
            3,
            error_type="Timeout",
            output_format=fmt,
            script_name="set_issue_labels.py",
            extra=data,
        )
        raise SystemExit(3) from err

    data = {
        "issue": args.issue,
        "applied": applied,
        "created": created,
        "removed": removed + removed_requested,
        "absent": absent,
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
        human_summary=(
            f"Applied {len(applied)} label(s), removed "
            f"{len(removed) + len(removed_requested)}, absent {len(absent)} "
            f"on issue #{args.issue}"
        ),
        status="PASS",
        script_name="set_issue_labels.py",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
