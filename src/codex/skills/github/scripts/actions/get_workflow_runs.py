#!/usr/bin/env python3
"""List GitHub Actions workflow runs with filters.

Covers the read side of run-level CI investigation: runs not tied to a pull
request (main-branch CI, workflow_dispatch, schedule), approval-waiting runs,
and failure archaeology. ``get_pr_checks.py`` answers PR-scoped questions;
this script answers run-scoped ones. Read-only.

Exit codes follow ADR-035. Reads only, so exit 1 cannot occur:
    0 - Runs listed; an empty list is a success, not an error
    2 - --status is not a known value, or --limit is not positive
    3 - The API read failed
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from skill_bootstrap import ensure_plugin_paths

ensure_plugin_paths(__file__, (".claude", "lib"))

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

_SCRIPT_NAME = "get_workflow_runs.py"

_VALID_STATUSES = {
    "completed",
    "action_required",
    "cancelled",
    "failure",
    "neutral",
    "skipped",
    "stale",
    "success",
    "timed_out",
    "in_progress",
    "queued",
    "requested",
    "waiting",
    "pending",
}

_MAX_LIMIT = 100


def normalize_run(run: dict) -> dict:
    return {
        "id": run.get("id"),
        "name": run.get("name"),
        "workflow": (run.get("workflow") or {}).get("name")
        if isinstance(run.get("workflow"), dict)
        else run.get("name"),
        "workflow_path": run.get("path"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "event": run.get("event"),
        "branch": run.get("head_branch"),
        "head_sha": run.get("head_sha"),
        "run_number": run.get("run_number"),
        "run_attempt": run.get("run_attempt"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "url": run.get("html_url"),
        "pull_requests": [
            {"number": pr.get("number"), "head_branch": (pr.get("head") or {}).get("ref")}
            for pr in run.get("pull_requests") or []
        ],
    }


def list_runs(
    owner: str,
    repo: str,
    *,
    workflow: str = "",
    branch: str = "",
    event: str = "",
    status: str = "",
    limit: int = 20,
) -> list[dict]:
    query = [f"per_page={min(limit, _MAX_LIMIT)}"]
    if branch:
        query.append(f"branch={urllib.parse.quote(branch, safe='')}")
    if event:
        query.append(f"event={urllib.parse.quote(event, safe='')}")
    if status:
        query.append(f"status={urllib.parse.quote(status, safe='')}")
    if workflow:
        endpoint = f"repos/{owner}/{repo}/actions/workflows/{workflow}/runs"
    else:
        endpoint = f"repos/{owner}/{repo}/actions/runs"
    result = subprocess.run(
        ["gh", "api", endpoint + "?" + "&".join(query)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or result.stdout.strip()
            or "gh api actions/runs failed with no stderr or stdout output"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to decode runs response: {exc}") from exc
    return payload.get("workflow_runs") or []


_HELP_EPILOG = """\
examples:
  %(prog)s --limit 10
  %(prog)s --workflow pytest.yml --branch main --status completed --limit 5
  %(prog)s --status waiting --branch main

exit codes:
  0  success
  2  usage or configuration error
  3  external service or API error
  4  auth error
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="List workflow runs with filters.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--owner", default="")
    p.add_argument("--repo", default="")
    p.add_argument(
        "--workflow",
        default="",
        help="Workflow ID or filename (for example pytest.yml); omit for all workflows",
    )
    p.add_argument("--branch", default="", help="Filter by branch")
    p.add_argument("--event", default="", help="Filter by event (push, pull_request, ...)")
    p.add_argument(
        "--status",
        default="",
        help="Filter by status or conclusion (waiting, in_progress, failure, ...)",
    )
    p.add_argument(
        "--pull-request",
        type=int,
        default=0,
        help="Client-side filter: keep only runs associated with this PR number",
    )
    p.add_argument("--limit", type=int, default=20, help="Max runs to return (cap 100)")
    add_output_format_arg(p)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated(rest_only=True)
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    if args.status and args.status not in _VALID_STATUSES:
        write_skill_error(
            f"--status must be one of {sorted(_VALID_STATUSES)}",
            2,
            error_type="InvalidParams",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
        )
        return 2
    if args.limit < 1:
        write_skill_error(
            "--limit must be positive",
            2,
            error_type="InvalidParams",
            output_format=fmt,
            script_name=_SCRIPT_NAME,
        )
        return 2

    # A client-side PR filter must scan before the limit cut: an older matching
    # run never enters a page already truncated to --limit. Fetch the full page
    # (one page only; deeper pagination is documented in the output), filter,
    # then truncate.
    fetch_limit = _MAX_LIMIT if args.pull_request else args.limit
    try:
        runs = list_runs(
            owner,
            repo,
            workflow=args.workflow,
            branch=args.branch,
            event=args.event,
            status=args.status,
            limit=fetch_limit,
        )
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        write_skill_error(
            str(exc), 3, error_type="ApiError", output_format=fmt, script_name=_SCRIPT_NAME
        )
        return 3

    # A full page under a plain --limit listing is the truncation the caller
    # asked for, so it carries no signal. The flag fires only when the scan was
    # truncated in a way nobody requested: a PR filter scanning one page.
    scan_capped = bool(args.pull_request) and len(runs) >= min(fetch_limit, _MAX_LIMIT)
    if args.pull_request:
        runs = [
            run
            for run in runs
            if any(pr.get("number") == args.pull_request for pr in run.get("pull_requests") or [])
        ]
    normalized = [normalize_run(run) for run in runs[: args.limit]]

    write_skill_output(
        {
            "runs": normalized,
            "count": len(normalized),
            "scan_capped": scan_capped,
            "filters": {
                "workflow": args.workflow or None,
                "branch": args.branch or None,
                "event": args.event or None,
                "status": args.status or None,
                "pull_request": args.pull_request or None,
            },
        },
        output_format=fmt,
        human_summary=(
            f"{len(normalized)} workflow run(s)"
            + (" (scan capped at first page; older runs not scanned)" if scan_capped else "")
        ),
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
