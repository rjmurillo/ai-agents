"""Detect velocity opportunities by running velocity_accelerator.py.

Replaces the inline PowerShell block in velocity-accelerator.yml
(ADR-006: no logic in YAML). Builds the argument list from env vars,
calls scripts/velocity_accelerator.py, parses its JSON output, and
writes opportunities and count to GITHUB_OUTPUT.

EXIT CODES (ADR-035):
  0  - Success (including zero-opportunities case)
  1  - velocity_accelerator.py reported a configuration error (exit 2)
  2  - Configuration error (GITHUB_OUTPUT not set)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_CONFIG = 2


def build_accelerator_args(env: dict[str, str]) -> list[str]:
    """Build the positional argument list for velocity_accelerator.py."""
    args = [
        "scripts/velocity_accelerator.py",
        "--event",
        env.get("EVENT_NAME", ""),
        "--output-format",
        "json",
    ]

    if event_action := env.get("EVENT_ACTION", ""):
        args += ["--action", event_action]

    if pr_number := env.get("PR_NUMBER", ""):
        args += ["--pr-number", pr_number]

    if env.get("PR_MERGED", "") == "true":
        args.append("--pr-merged")

    if issue_number := env.get("ISSUE_NUMBER", ""):
        args += ["--issue-number", issue_number]

    if issue_title := env.get("ISSUE_TITLE", ""):
        args += ["--issue-title", issue_title]

    if issue_body := env.get("ISSUE_BODY", ""):
        args += ["--issue-body", issue_body]

    return args


def main() -> int:
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if not output_path:
        print("ERROR: GITHUB_OUTPUT not set", file=sys.stderr)
        return EXIT_CONFIG

    env = dict(os.environ)

    # Forward SHA env vars that velocity_accelerator.py reads directly.
    before_sha = env.pop("BEFORE_SHA", "")
    after_sha = env.pop("AFTER_SHA", "")
    if before_sha:
        env["GITHUB_EVENT_BEFORE"] = before_sha
    if after_sha:
        env["GITHUB_SHA"] = after_sha

    args = build_accelerator_args(env)
    result = subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    if result.returncode == 2:
        print("::error::Configuration error running velocity accelerator", file=sys.stderr)
        return EXIT_FAILURE

    try:
        opportunities = json.loads(result.stdout)
        if not isinstance(opportunities, list):
            opportunities = []
    except (json.JSONDecodeError, ValueError):
        opportunities = []

    count = len(opportunities)
    opportunities_json = json.dumps(opportunities, separators=(",", ":"))

    with open(output_path, "a", encoding="utf-8") as f:
        f.write(f"opportunities={opportunities_json}\n")
        f.write(f"count={count}\n")

    print(f"Detected {count} velocity opportunities")
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
