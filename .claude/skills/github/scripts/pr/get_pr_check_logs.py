#!/usr/bin/env python3
"""Fetch logs from failing GitHub Actions checks on a Pull Request.

Retrieves failure logs from GitHub Actions workflow runs associated with
failing PR checks. Extracts relevant failure snippets with configurable context.

Supports standalone mode (provide --pull-request) and pipeline mode
(provide --checks-input with JSON from get_pr_checks.py).

Exit codes follow ADR-035:
    0 - Success (logs retrieved, or no failing checks)
    1 - Invalid parameters
    2 - PR not found
    3 - API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
    resolve_repo_params,
)

# ---------------------------------------------------------------------------
# Failure detection patterns
# ---------------------------------------------------------------------------

_FAILURE_PATTERNS = [
    r"\berror\b",
    r"\bfail(ed|ure|ing)?\b",
    r"\btraceback\b",
    r"\bexception\b",
    r"\bpanic\b",
    r"\bfatal\b",
    r"\btimeout\b",
    r"ERROR:",
    r"##\[error\]",
    r"Process completed with exit code [1-9]",
    r"\bsegmentation fault\b",
    r"\bstack trace\b",
    r"\bassertion failed\b",
]

_COMBINED_PATTERN = re.compile("|".join(_FAILURE_PATTERNS), re.IGNORECASE)


# ---------------------------------------------------------------------------
# URL parsing helpers
# ---------------------------------------------------------------------------


def get_run_id_from_url(url: str) -> str | None:
    """Extract workflow run ID from a GitHub Actions URL."""
    match = re.search(r"/actions/runs/(\d+)", url)
    return match.group(1) if match else None


def get_job_id_from_url(url: str) -> str | None:
    """Extract job ID from a GitHub Actions URL."""
    match = re.search(r"/job/(\d+)", url)
    return match.group(1) if match else None


def is_github_actions_url(url: str) -> bool:
    """Check if URL points to GitHub Actions."""
    return bool(re.search(r"github\.com/.+/actions/runs/", url or ""))


# ---------------------------------------------------------------------------
# Log fetching and parsing
# ---------------------------------------------------------------------------


def get_failure_snippets(
    log_lines: list[str], context_lines: int, max_lines: int,
) -> list[dict]:
    """Extract failure snippets from log content with context."""
    snippets: list[dict] = []
    total_extracted = 0
    i = 0

    while i < len(log_lines) and total_extracted < max_lines:
        line = log_lines[i]
        if _COMBINED_PATTERN.search(line):
            start = max(0, i - context_lines)
            end = min(len(log_lines) - 1, i + context_lines)

            snippet_lines = log_lines[start : end + 1]
            lines_available = max_lines - total_extracted
            if len(snippet_lines) > lines_available:
                snippet_lines = snippet_lines[:lines_available]

            snippets.append({
                "LineNumber": i + 1,
                "MatchedLine": line.strip(),
                "Context": "\n".join(snippet_lines),
                "StartLine": start + 1,
                "EndLine": start + len(snippet_lines),
            })

            total_extracted += len(snippet_lines)
            i = end + 1
        else:
            i += 1

    return snippets


def fetch_workflow_run_logs(
    owner: str, repo: str, run_id: str, job_id: str | None,
) -> dict:
    """Fetch logs for a GitHub Actions workflow run."""
    # Try job-specific logs first
    if job_id:
        result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/actions/jobs/{job_id}/logs"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout:
            return {"Success": True, "Content": result.stdout, "Source": "job"}

    # Fall back to run view --log-failed
    result = subprocess.run(
        ["gh", "run", "view", run_id, "--repo", f"{owner}/{repo}", "--log-failed"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode == 0 and result.stdout:
        return {"Success": True, "Content": result.stdout, "Source": "run-failed"}

    # Try full log
    result = subprocess.run(
        ["gh", "run", "view", run_id, "--repo", f"{owner}/{repo}", "--log"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode == 0 and result.stdout:
        return {"Success": True, "Content": result.stdout, "Source": "run-full"}

    return {
        "Success": False,
        "Error": f"Failed to fetch logs: {result.stderr}",
        "Source": "none",
    }


def get_check_logs(
    owner: str,
    repo: str,
    failing_checks: list[dict],
    max_lines: int,
    context_lines: int,
) -> list[dict]:
    """Fetch logs for all failing checks."""
    results: list[dict] = []

    for check in failing_checks:
        check_result: dict = {
            "Name": check.get("Name", ""),
            "DetailsUrl": check.get("DetailsUrl", ""),
            "State": check.get("State", ""),
            "Conclusion": check.get("Conclusion", ""),
        }

        details_url = check.get("DetailsUrl", "")

        if not is_github_actions_url(details_url):
            check_result["LogSource"] = "external"
            check_result["Note"] = "External CI system, logs not accessible via GitHub API"
            check_result["Snippets"] = []
            results.append(check_result)
            continue

        run_id = get_run_id_from_url(details_url)
        job_id = get_job_id_from_url(details_url)

        if not run_id:
            check_result["LogSource"] = "error"
            check_result["Error"] = "Could not extract run ID from URL"
            check_result["Snippets"] = []
            results.append(check_result)
            continue

        check_result["RunId"] = run_id
        if job_id:
            check_result["JobId"] = job_id

        log_result = fetch_workflow_run_logs(owner, repo, run_id, job_id)

        if not log_result["Success"]:
            check_result["LogSource"] = "error"
            check_result["Error"] = log_result.get("Error", "Unknown error")
            check_result["Snippets"] = []
            results.append(check_result)
            continue

        check_result["LogSource"] = log_result["Source"]

        content = log_result["Content"]
        log_lines = content.splitlines() if isinstance(content, str) else content

        snippets = get_failure_snippets(log_lines, context_lines, max_lines)
        check_result["Snippets"] = snippets
        check_result["TotalLogLines"] = len(log_lines)

        results.append(check_result)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch logs from failing GitHub Actions checks on a PR.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, default=0,
        help="PR number (standalone mode)",
    )
    parser.add_argument(
        "--checks-input", default="",
        help="JSON string from get_pr_checks.py output (pipeline mode). Use '-' for stdin.",
    )
    parser.add_argument(
        "--max-lines", type=int, default=160,
        help="Maximum lines to extract per failure snippet (default: 160)",
    )
    parser.add_argument(
        "--context-lines", type=int, default=30,
        help="Lines of context before/after failure markers (default: 30)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved.owner
    repo = resolved.repo

    pr_number = args.pull_request
    failing_checks: list[dict] = []

    checks_input = args.checks_input
    if checks_input == "-":
        checks_input = sys.stdin.read()

    if checks_input:
        # Pipeline mode
        try:
            checks_data = json.loads(checks_input)
        except json.JSONDecodeError as exc:
            output = {"Success": False, "Error": f"Failed to parse checks input: {exc}"}
            print(json.dumps(output, indent=2))
            return 1

        if not checks_data.get("Success"):
            output = {
                "Success": False,
                "Error": f"Input checks data indicates failure: {checks_data.get('Error', '')}",
            }
            print(json.dumps(output, indent=2))
            return 1

        if checks_data.get("Number") and pr_number == 0:
            pr_number = checks_data["Number"]

        failing_checks = [
            c for c in checks_data.get("Checks", [])
            if c.get("Conclusion") in ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED")
        ]

    elif pr_number > 0:
        # Standalone mode - fetch checks first
        checks_script = os.path.join(os.path.dirname(__file__), "get_pr_checks.py")
        result = subprocess.run(
            [
                sys.executable, checks_script,
                "--owner", owner, "--repo", repo,
                "--pull-request", str(pr_number),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Exit codes 2, 3, 7 are actual errors
        if result.returncode in (2, 3, 7):
            print(result.stdout)
            return result.returncode

        try:
            checks_data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            output = {"Success": False, "Error": f"Failed to parse checks response: {exc}"}
            print(json.dumps(output, indent=2))
            return 3

        if not checks_data.get("Success"):
            print(result.stdout)
            return 2

        failing_checks = [
            c for c in checks_data.get("Checks", [])
            if c.get("Conclusion") in ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED")
        ]
    else:
        output = {
            "Success": False,
            "Error": "Either --pull-request or --checks-input is required",
        }
        print(json.dumps(output, indent=2))
        return 1

    # No failing checks
    if not failing_checks:
        output = {
            "Success": True,
            "Owner": owner,
            "Repo": repo,
            "PullRequest": pr_number,
            "FailingChecks": 0,
            "Message": "No failing checks found",
            "CheckLogs": [],
        }
        print(json.dumps(output, indent=2))
        print("No failing checks to analyze", file=sys.stderr)
        return 0

    # Fetch logs
    check_logs = get_check_logs(
        owner, repo, failing_checks, args.max_lines, args.context_lines,
    )

    output = {
        "Success": True,
        "Owner": owner,
        "Repo": repo,
        "PullRequest": pr_number,
        "FailingChecks": len(failing_checks),
        "CheckLogs": check_logs,
    }
    print(json.dumps(output, indent=2))

    # Summary
    logs_found = sum(1 for cl in check_logs if cl.get("Snippets"))
    external = sum(1 for cl in check_logs if cl.get("LogSource") == "external")

    if external > 0:
        print(
            f"Analyzed {len(failing_checks)} failing check(s): "
            f"{logs_found} with logs, {external} external (logs not accessible)",
            file=sys.stderr,
        )
    else:
        print(
            f"Analyzed {len(failing_checks)} failing check(s) "
            f"with {logs_found} containing failure snippets",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
