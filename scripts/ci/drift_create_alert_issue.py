#!/usr/bin/env python3
"""Create a GitHub issue when agent drift is detected.

Replaces the inline heredoc shell in drift-detection.yml (ADR-006).
Loads the body template from .github/prompts/drift-alert-issue.md, substitutes
runtime values (date, server URL, repository, run ID, and drift details), then
calls `gh issue create`.

ENV (required in the calling step):
  RUNNER_TEMP (or ".") - directory where drift-details.md was written
  SERVER_URL           - ${{ github.server_url }}
  REPOSITORY           - ${{ github.repository }}
  RUN_ID               - ${{ github.run_id }}
  GH_TOKEN             - set by caller for gh CLI auth

EXIT CODES (ADR-035):
  0 - issue created
  2 - template or drift details missing
  3 - GitHub issue creation failed
"""

from __future__ import annotations

import os
import string
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

_TEMPLATE_PATH = Path(".github/prompts/drift-alert-issue.md")


def run(_argv: list[str] | None = None) -> int:
    """Create the drift alert issue."""
    runner_temp = os.environ.get("RUNNER_TEMP", ".")
    server_url = os.environ.get("SERVER_URL", os.environ.get("GITHUB_SERVER_URL", ""))
    repository = os.environ.get("REPOSITORY", os.environ.get("GITHUB_REPOSITORY", ""))
    run_id = os.environ.get("RUN_ID", os.environ.get("GITHUB_RUN_ID", ""))

    if not _TEMPLATE_PATH.exists():
        print(f"::error::template not found: {_TEMPLATE_PATH}", file=sys.stderr)
        return EXIT_CONFIG

    tmpl = string.Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))

    details_path = Path(runner_temp) / "drift-details.md"
    if not details_path.is_file():
        print(f"::error::drift details not found: {details_path}", file=sys.stderr)
        return EXIT_CONFIG
    drift_details = details_path.read_text(encoding="utf-8")
    if not drift_details.strip():
        print(f"::error::drift details are empty: {details_path}", file=sys.stderr)
        return EXIT_CONFIG

    now = datetime.now(UTC)
    body = tmpl.substitute(
        DETECTION_DATE=now.strftime("%Y-%m-%d %H:%M UTC"),
        SERVER_URL=server_url,
        REPOSITORY=repository,
        RUN_ID=run_id,
        DRIFT_DETAILS=drift_details,
    )

    issue_body_path = Path(runner_temp) / "issue-body.md"
    issue_body_path.write_text(body, encoding="utf-8")

    title = f"Agent Drift Detected - {now.strftime('%Y-%m-%d')}"
    try:
        sys.stdout.flush()
        result = subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--title",
                title,
                "--body-file",
                str(issue_body_path),
                "--label",
                "drift-detected,automated",
            ],
            check=False,
        )
    except OSError as exc:
        print(f"::error::failed to launch gh issue create: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    if result.returncode != 0:
        print("::error::gh issue create failed", file=sys.stderr)
        return EXIT_EXTERNAL
    return EXIT_OK


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
