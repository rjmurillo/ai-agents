#!/usr/bin/env python3
"""Wrap spec_external_signal_gate.py and surface output in the step summary.

Replaces the bash 'External-signal gate' block in
ai-spec-validation.yml (ADR-006).

ENV:
  PR_BODY              - PR body text (used as fallback if no PR_BODY_FILE)
  PR_NUMBER            - PR number for gh CLI fallback
  GITHUB_REPOSITORY    - owner/repo
  GITHUB_RUN_ID        - workflow run ID
  GITHUB_RUN_ATTEMPT   - workflow run attempt
  RUNNER_TEMP          - temp directory (default ".")
  GITHUB_STEP_SUMMARY  - path to the step summary file
  TRACE_VERDICT        - trace step verdict (passed to gate via env)
  COMPLETENESS_VERDICT - completeness step verdict

EXIT CODES (ADR-035):
  0   - gate passed or was skipped
  N>0 - gate returned non-zero (signals observation failure)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _pr_body_fallback(pr_number: str, repository: str) -> str:
    if not pr_number or not repository:
        return ""
    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            pr_number,
            "--repo",
            repository,
            "--json",
            "body",
            "-q",
            ".body",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def run(_argv: list[str] | None = None) -> int:
    """Run the external signal gate and append results to step summary."""
    pr_body = os.environ.get("PR_BODY", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "0")
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "0")
    runner_temp = os.environ.get("RUNNER_TEMP", ".")
    summary_file_path = os.environ.get("GITHUB_STEP_SUMMARY", "")

    if not pr_body and pr_number:
        pr_body = _pr_body_fallback(pr_number, repository)

    body_file = Path(runner_temp) / f"pr-body-signal-{run_id}-{run_attempt}.md"
    summary_out = Path(runner_temp) / f"external-gate-{run_id}-{run_attempt}.json"

    body_file.write_text(pr_body, encoding="utf-8")

    env = os.environ.copy()
    env["PR_BODY_FILE"] = str(body_file)

    result = subprocess.run(
        [sys.executable, "scripts/quality_gate/spec_external_signal_gate.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    gate_rc = result.returncode

    # Write gate output to summary_out and print it (mirrors tee behaviour)
    gate_output = result.stdout
    if result.stderr:
        gate_output += result.stderr
    print(gate_output, end="")
    summary_out.write_text(gate_output, encoding="utf-8")

    # Append to GITHUB_STEP_SUMMARY
    if summary_file_path:
        summary_json = (
            summary_out.read_text(encoding="utf-8") if summary_out.exists() else "(no output)"
        )
        with open(summary_file_path, "a", encoding="utf-8") as fh:
            fh.write("### External-signal gate (observe)\n\n```json\n")
            fh.write(summary_json)
            fh.write("\n```\n")

    # Clean up
    body_file.unlink(missing_ok=True)
    summary_out.unlink(missing_ok=True)

    return gate_rc


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
