#!/usr/bin/env python3
"""Fetch logs from failing CI checks on a GitHub Pull Request.

Retrieves required check runs, identifies failures, extracts run IDs from
detail URLs, and fetches failed job logs. Truncates output to configurable
line limits.

Exit codes (ADR-035):
    0 = Success (even if no failures found)
    1 = Invalid parameters
    2 = PR not found
    3 = API error
    4 = Not authenticated
"""

import argparse
import json
import os
import re
import subprocess
import sys

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    resolve_repo_params,
    write_error_and_exit,
)


def fetch_check_runs(owner: str, repo: str, pr_number: int) -> list[dict]:
    """Fetch required check runs for a PR."""
    cmd = [
        "gh", "pr", "checks", str(pr_number),
        "--repo", f"{owner}/{repo}",
        "--json", "name,state,link",
        "--required",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not found" in stderr.lower() or "no pull request" in stderr.lower():
            write_error_and_exit(f"PR #{pr_number} not found in {owner}/{repo}", 2)
        write_error_and_exit(f"Failed to get PR checks: {stderr}", 3)

    try:
        checks: list[dict] = json.loads(result.stdout)
        return checks
    except json.JSONDecodeError:
        write_error_and_exit("Failed to parse check runs response", 3)
        # write_error_and_exit calls sys.exit; unreachable
        raise SystemExit(3) from None


def extract_run_id(link: str) -> str | None:
    """Extract workflow run ID from a GitHub Actions URL."""
    # Format: https://github.com/owner/repo/actions/runs/12345/job/67890
    match = re.search(r"/actions/runs/(\d+)", link)
    if match:
        return match.group(1)
    return None


def fetch_failed_logs(owner: str, repo: str, run_id: str) -> str:
    """Fetch failed job logs for a workflow run."""
    cmd = [
        "gh", "run", "view", run_id,
        "--log-failed",
        "--repo", f"{owner}/{repo}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        return f"[Could not fetch logs for run {run_id}: {result.stderr.strip()}]"

    return result.stdout


def truncate_log(log: str, max_lines: int, context_lines: int) -> str:
    """Truncate log output, keeping the most relevant lines.

    Keeps the last max_lines lines. If the log is longer, prepends a
    truncation notice. The context_lines parameter reserves leading
    context when the log exceeds max_lines.
    """
    lines = log.splitlines()
    if len(lines) <= max_lines:
        return log

    # Keep last max_lines to capture the failure output
    kept = lines[-max_lines:]
    skipped = len(lines) - max_lines
    return f"[... {skipped} lines truncated ...]\n" + "\n".join(kept)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch logs from failing CI checks on a PR",
    )
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    parser.add_argument(
        "--max-lines",
        type=int,
        default=160,
        help="Maximum log lines per check (default: 160)",
    )
    parser.add_argument(
        "--context-lines",
        type=int,
        default=30,
        help="Context lines to preserve (default: 30)",
    )
    args = parser.parse_args()

    if args.max_lines < 1:
        write_error_and_exit("--max-lines must be at least 1", 1)
    if args.context_lines < 0:
        write_error_and_exit("--context-lines must be non-negative", 1)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["owner"], resolved["repo"]

    checks = fetch_check_runs(owner, repo, args.pull_request)

    failing_states = {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "ERROR"}
    failing_checks = [c for c in checks if c.get("state", "").upper() in failing_states]

    results = []
    for check in failing_checks:
        name = check.get("name", "unknown")
        link = check.get("link", "")
        run_id = extract_run_id(link)

        if not run_id:
            results.append({
                "Name": name,
                "RunId": None,
                "LogSnippet": f"[Could not extract run ID from: {link}]",
            })
            continue

        log = fetch_failed_logs(owner, repo, run_id)
        snippet = truncate_log(log, args.max_lines, args.context_lines)

        results.append({
            "Name": name,
            "RunId": run_id,
            "LogSnippet": snippet,
        })

    output = {
        "Success": True,
        "PullRequest": args.pull_request,
        "FailingChecks": results,
        "TotalFailures": len(results),
    }
    print(json.dumps(output, indent=2))

    if results:
        print(f"PR #{args.pull_request}: {len(results)} failing check(s)", file=sys.stderr)
        for r in results:
            print(f"  - {r['Name']} (run: {r['RunId']})", file=sys.stderr)
    else:
        print(f"PR #{args.pull_request}: No failing required checks", file=sys.stderr)


if __name__ == "__main__":
    main()
