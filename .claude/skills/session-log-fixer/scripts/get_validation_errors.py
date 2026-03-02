#!/usr/bin/env python3
"""Extract validation errors from GitHub Actions Job Summary.

Reads the Job Summary from a failed Session Protocol Validation workflow run
and extracts specific validation errors to guide fixes.

Exit Codes:
    0  - Success: Errors extracted
    1  - Error: Run not found or gh command failed
    2  - Error: No validation errors found in Job Summary

See: ADR-035 Exit Code Standardization
Requires: gh CLI authenticated
"""

import argparse
import json
import re
import subprocess
import sys


def run_gh(args: list[str]) -> str:
    """Run a gh CLI command and return stdout."""
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh command failed (exit {result.returncode}): {result.stderr}"
        )
    return result.stdout


def get_run_id_from_pr(pr_number: int) -> str:
    """Get the latest failed validation run ID for a PR."""
    pr_info = json.loads(run_gh(["pr", "view", str(pr_number), "--json", "headRefName"]))
    branch = pr_info["headRefName"]

    runs_json = run_gh([
        "run", "list",
        "--branch", branch,
        "--workflow", "session-protocol-validation.yml",
        "--limit", "5",
        "--json", "databaseId,conclusion",
    ])
    runs = json.loads(runs_json)

    for run in runs:
        if run.get("conclusion") == "failure":
            return str(run["databaseId"])

    raise RuntimeError(
        f"No failed Session Protocol validation runs found for PR #{pr_number}"
    )


def parse_job_summary(summary: str) -> dict:
    """Parse validation errors from job summary text."""
    result = {
        "OverallVerdict": None,
        "MustFailureCount": 0,
        "NonCompliantSessions": [],
        "DetailedErrors": {},
    }

    # Extract overall verdict
    verdict_match = re.search(r"Overall Verdict:\s*\*\*([A-Z_]+)\*\*", summary)
    if verdict_match:
        result["OverallVerdict"] = verdict_match.group(1)

    # Extract MUST failure count
    must_match = re.search(r"(\d+)\s+MUST requirement\(s\) not met", summary)
    if must_match:
        result["MustFailureCount"] = int(must_match.group(1))

    # Extract non-compliant sessions from table
    lines = summary.split("\n")
    in_table = False
    current_session = None

    for line in lines:
        if re.search(r"^\|\s*Session File\s*\|", line):
            in_table = True
            continue

        if in_table:
            session_match = re.search(
                r"^\|\s*`([^`]+)`\s*\|\s*[^\|]*NON_COMPLIANT\s*\|\s*(\d+)\s*\|",
                line,
            )
            if session_match:
                result["NonCompliantSessions"].append({
                    "File": session_match.group(1),
                    "MustFailures": int(session_match.group(2)),
                })
            elif not re.match(r"^\|", line) or re.match(r"^---", line):
                in_table = False

        # Extract detailed errors from expandable sections
        summary_match = re.search(r"<summary>[^\s]*\s*([^<]+)</summary>", line)
        if summary_match:
            current_session = summary_match.group(1).strip()
            result["DetailedErrors"][current_session] = []

        detail_match = re.search(
            r"^\|\s*([^|]+)\s*\|\s*MUST\s*\|\s*FAIL\s*\|\s*([^|]+)\s*\|", line
        )
        if detail_match and current_session:
            result["DetailedErrors"][current_session].append({
                "Check": detail_match.group(1).strip(),
                "Issue": detail_match.group(2).strip(),
            })

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract validation errors from GitHub Actions Job Summary."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--run-id",
        type=str,
        help="GitHub Actions run ID to fetch errors from.",
    )
    group.add_argument(
        "--pull-request",
        type=int,
        help="PR number (finds latest failing run for the PR branch).",
    )
    parser.parse_args()
    args = parser.parse_args()

    # Resolve run ID
    try:
        if args.pull_request:
            target_run_id = get_run_id_from_pr(args.pull_request)
        else:
            target_run_id = args.run_id
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        print(f"Failed to extract validation errors: {e}", file=sys.stderr)
        sys.exit(1)

    # Fetch job log
    try:
        jobs_json = run_gh(["run", "view", target_run_id, "--json", "jobs"])
        jobs = json.loads(jobs_json)
    except (RuntimeError, subprocess.TimeoutExpired):
        print(
            "Failed to extract validation errors: Unable to fetch run details",
            file=sys.stderr,
        )
        sys.exit(1)

    # Find Aggregate Results job
    aggregate_job = None
    for job in jobs.get("jobs", []):
        if "Aggregate Results" in job.get("name", ""):
            aggregate_job = job
            break

    if not aggregate_job:
        print(
            f"No 'Aggregate Results' job found in run {target_run_id}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Get job log
    try:
        job_log = run_gh(["run", "view", target_run_id, "--log-failed"])
    except (RuntimeError, subprocess.TimeoutExpired):
        print(
            "Failed to extract validation errors: Unable to fetch job log",
            file=sys.stderr,
        )
        sys.exit(1)

    # Parse errors
    parsed_errors = parse_job_summary(job_log)

    if not parsed_errors["NonCompliantSessions"]:
        print(
            f"No validation errors found in Job Summary for run {target_run_id}",
            file=sys.stderr,
        )
        sys.exit(2)

    # Output
    output = {
        "RunId": target_run_id,
        "OverallVerdict": parsed_errors["OverallVerdict"],
        "MustFailureCount": parsed_errors["MustFailureCount"],
        "NonCompliantSessions": parsed_errors["NonCompliantSessions"],
        "DetailedErrors": parsed_errors["DetailedErrors"],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
