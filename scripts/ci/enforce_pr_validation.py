#!/usr/bin/env python3
"""Enforce blocking PR validation results."""

from __future__ import annotations

import os
import subprocess
import sys

LOGIC_ERROR = 1
BYPASS_LABEL = "commit-limit-bypass"


def _fetch_labels(repository: str, pr_number: str) -> tuple[int, list[str]]:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/issues/{pr_number}/labels",
            "--jq",
            ".[].name",
        ],
        check=False,
        stdout=subprocess.PIPE,
        text=True,
    )
    labels = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return result.returncode, labels


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("::error::unexpected command line arguments", file=sys.stderr)
        return 2
    overall_status = os.environ.get("OVERALL_STATUS", "")
    commit_status = os.environ.get("COMMIT_STATUS", "")
    commit_count = os.environ.get("COMMIT_COUNT", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if overall_status in {"FAIL", "ERROR"}:
        print(f"::error::PR validation failed: {overall_status}", file=sys.stderr)
        return LOGIC_ERROR
    if commit_status == "BLOCKED":
        exit_code, labels = _fetch_labels(repository, pr_number)
        if exit_code != 0:
            print(
                f"::error::Failed to fetch PR labels (exit code: {exit_code})",
                file=sys.stderr,
            )
            return LOGIC_ERROR
        if BYPASS_LABEL in labels:
            print(f"::warning::Commit limit bypassed via '{BYPASS_LABEL}' label")
        else:
            print(
                f"::error::PR has {commit_count} commits (limit: 20). "
                f"Add '{BYPASS_LABEL}' label to override or split this PR.",
                file=sys.stderr,
            )
            return LOGIC_ERROR
    print("✓ PR validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
