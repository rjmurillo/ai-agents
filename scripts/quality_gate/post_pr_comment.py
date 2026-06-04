#!/usr/bin/env python3
"""Validate inputs, then post the quality-gate report as a PR comment.

Extracted from the inline ``Post PR Comment`` step in
``.github/workflows/ai-pr-quality-gate.yml`` (ADR-006: no logic in YAML).

The original bash block validated three preconditions then invoked the retry
wrapper around the comment poster:

    python3 .github/scripts/run_with_retry.py -- \
      python3 .github/scripts/post_issue_comment.py \
      --issue "$PR_NUMBER" --body-file "$REPORT_FILE" \
      --marker "AI-PR-QUALITY-GATE" --update-if-exists

This script reproduces that: it guards on PR_NUMBER, REPORT_FILE, and the file's
existence (exit 1 with ``::error::`` each), then spawns the same command and
propagates its exit code.

Integration-point note (release-it rule): the original invocation had no
timeout. This extraction adds a bounded ``--timeout`` (default 600s) on the
subprocess so a hung GitHub call cannot wedge the step indefinitely. The
workflow step keeps ``continue-on-error: true``, so a non-zero exit here does
not fail the gate.

Input env vars:
    PR_NUMBER    - the pull request number.
    REPORT_FILE  - path to the rendered report body file.
    GH_TOKEN     - GitHub token (consumed by the spawned poster).

Exit codes (ADR-035):
    0 - comment posted (poster returned 0)
    1 - missing PR_NUMBER/REPORT_FILE, report file absent, or poster failed
    3 - subprocess timed out (external/dependency failure)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GITHUB_SCRIPTS = _SCRIPT_DIR.parents[1] / ".github" / "scripts"

_MARKER = "AI-PR-QUALITY-GATE"


def build_command(pr_number: str, report_file: str) -> list[str]:
    """Return the run_with_retry + post_issue_comment argv (verbatim shape)."""

    return [
        sys.executable,
        str(_GITHUB_SCRIPTS / "run_with_retry.py"),
        "--",
        sys.executable,
        str(_GITHUB_SCRIPTS / "post_issue_comment.py"),
        "--issue",
        pr_number,
        "--body-file",
        report_file,
        "--marker",
        _MARKER,
        "--update-if-exists",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--timeout",
        type=float,
        default=600.0,
        help="Subprocess timeout in seconds (release-it: bound the call).",
    )
    args = parser.parse_args(argv)

    pr_number = os.environ.get("PR_NUMBER", "")
    report_file = os.environ.get("REPORT_FILE", "")

    if not pr_number:
        print("::error::PR_NUMBER environment variable is missing")
        return 1
    if not report_file:
        print("::error::REPORT_FILE environment variable is missing")
        return 1
    if not Path(report_file).is_file():
        print(f"::error::Report file not found: {report_file}")
        return 1

    command = build_command(pr_number, report_file)
    try:
        result = subprocess.run(command, timeout=args.timeout, check=False)
    except subprocess.TimeoutExpired:
        print(f"::error::Posting PR comment timed out after {args.timeout}s")
        return 3
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
