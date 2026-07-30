#!/usr/bin/env python3
"""Build and post the AI issue triage summary comment."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import build_triage_summary_comment

CONFIG_ERROR = 2
DEFAULT_OUTPUT = Path(os.environ.get("RUNNER_TEMP", ".")) / "triage-comment.md"


def post_comment(*, issue_number: str, body_file: Path) -> int:
    sys.stdout.flush()
    result = subprocess.run(
        [
            "python3",
            ".github/scripts/run_with_retry.py",
            "--",
            "python3",
            ".github/scripts/post_issue_comment.py",
            "--issue",
            issue_number,
            "--body-file",
            str(body_file),
            "--marker",
            "AI-ISSUE-TRIAGE",
        ],
        check=False,
    )
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("::error::unexpected command line arguments", file=sys.stderr)
        return CONFIG_ERROR
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    if not issue_number:
        print("::error::ISSUE_NUMBER is required", file=sys.stderr)
        return CONFIG_ERROR
    output = DEFAULT_OUTPUT
    build_result = cast(int, build_triage_summary_comment.main(["--output", str(output)]))
    if build_result != 0:
        return build_result
    return post_comment(issue_number=issue_number, body_file=output)


if __name__ == "__main__":
    raise SystemExit(main())
