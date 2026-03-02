#!/usr/bin/env python3
"""Extract validation errors from GitHub Actions Job Summary.

Reads the Job Summary from a failed Session Protocol Validation workflow run
and extracts the specific validation errors to guide fixes.

Exit codes follow ADR-035:
    0 - Success (errors extracted)
    1 - Run not found or gh command failed
    2 - No validation errors found in Job Summary
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract validation errors from GitHub Actions Job Summary.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--run-id", help="GitHub Actions run ID to fetch errors from.",
    )
    group.add_argument(
        "--pull-request", type=int,
        help="PR number (will find latest failing run for the PR branch).",
    )
    return parser


def _get_run_id_from_pr(pr_number: int) -> str:
    """Get the latest failed validation run ID for a PR."""
    pr_result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "headRefName"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if pr_result.returncode != 0:
        msg = f"Failed to get PR #{pr_number} info"
        raise RuntimeError(msg)

    pr_info = json.loads(pr_result.stdout)
    branch = pr_info["headRefName"]

    runs_result = subprocess.run(
        ["gh", "run", "list", "--branch", branch,
         "--workflow", "session-protocol-validation.yml",
         "--limit", "5", "--json", "databaseId,conclusion"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if runs_result.returncode != 0:
        msg = "Failed to list workflow runs"
        raise RuntimeError(msg)

    runs = json.loads(runs_result.stdout)
    for run in runs:
        if run.get("conclusion") == "failure":
            return str(run["databaseId"])

    msg = f"No failed Session Protocol validation runs found for PR #{pr_number}"
    raise RuntimeError(msg)


def _parse_job_summary(summary: str) -> dict:
    """Parse validation errors from job summary text."""
    result: dict = {
        "overall_verdict": None,
        "must_failure_count": 0,
        "non_compliant_sessions": [],
        "detailed_errors": {},
    }

    m = re.search(r"Overall Verdict:\s*\*\*([A-Z_]+)\*\*", summary)
    if m:
        result["overall_verdict"] = m.group(1)

    m = re.search(r"(\d+)\s+MUST requirement\(s\) not met", summary)
    if m:
        result["must_failure_count"] = int(m.group(1))

    current_session = None
    in_table = False
    for line in summary.splitlines():
        if re.search(r"^\|\s*Session File\s*\|", line):
            in_table = True
            continue

        if in_table:
            m = re.match(r"\|\s*`([^`]+)`\s*\|\s*.*NON_COMPLIANT\s*\|\s*(\d+)\s*\|", line)
            if m:
                result["non_compliant_sessions"].append({
                    "file": m.group(1),
                    "must_failures": int(m.group(2)),
                })
            elif not re.match(r"^\|", line) or re.match(r"^---", line):
                in_table = False

        m = re.search(r"<summary>.*?\s*([^<]+)</summary>", line)
        if m:
            current_session = m.group(1).strip()
            result["detailed_errors"][current_session] = []

        m = re.match(r"\|\s*([^|]+)\s*\|\s*MUST\s*\|\s*FAIL\s*\|\s*([^|]+)\s*\|", line)
        if m and current_session:
            result["detailed_errors"][current_session].append({
                "check": m.group(1).strip(),
                "issue": m.group(2).strip(),
            })

    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Resolve run ID
    if args.pull_request:
        try:
            target_run_id = _get_run_id_from_pr(args.pull_request)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    else:
        target_run_id = args.run_id

    # Fetch job log
    try:
        log_result = subprocess.run(
            ["gh", "run", "view", target_run_id, "--log-failed"],
            capture_output=True, text=True, timeout=60, check=False,
        )
        if log_result.returncode != 0:
            print(f"ERROR: Unable to fetch run details for {target_run_id}", file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    parsed = _parse_job_summary(log_result.stdout)

    if not parsed["non_compliant_sessions"]:
        print(
            f"WARNING: No validation errors found in Job Summary for run {target_run_id}",
            file=sys.stderr,
        )
        return 2

    output = {
        "run_id": target_run_id,
        "overall_verdict": parsed["overall_verdict"],
        "must_failure_count": parsed["must_failure_count"],
        "non_compliant_sessions": parsed["non_compliant_sessions"],
        "detailed_errors": parsed["detailed_errors"],
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
