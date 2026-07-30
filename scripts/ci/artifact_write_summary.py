#!/usr/bin/env python3
"""Write artifact insight scanner results to GITHUB_STEP_SUMMARY.

Replaces the bash 'Generate summary' block in
artifact-insight-scanner.yml (ADR-006).

ENV:
  ARTIFACT_COUNT      - number of artifacts scanned
  FINDING_COUNT       - number of insights found
  DRY_RUN             - "true" if dry run mode
  VERDICT             - AI verdict
  GITHUB_STEP_SUMMARY - path to the step summary file

EXIT CODES (ADR-035):
  0 - summary written
"""

from __future__ import annotations

import os
import sys


def build_summary(
    artifact_count: str,
    finding_count: str,
    verdict: str,
    dry_run: str,
) -> str:
    """Return the markdown summary string."""
    lines = [
        "## Artifact Insight Scanner Results",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Artifacts Scanned | {artifact_count} |",
        f"| Insights Found | {finding_count} |",
        f"| AI Verdict | {verdict} |",
        f"| Dry Run | {dry_run} |",
        "",
    ]
    if dry_run == "true":
        lines += [
            "> [!NOTE]",
            "> Dry run mode - no issues were created",
        ]
    return "\n".join(lines) + "\n"


def run(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Write the summary to GITHUB_STEP_SUMMARY."""
    artifact_count = os.environ.get("ARTIFACT_COUNT", "0")
    finding_count = os.environ.get("FINDING_COUNT", "0")
    dry_run = os.environ.get("DRY_RUN", "false")
    verdict = os.environ.get("VERDICT", "N/A")
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY", "")

    content = build_summary(artifact_count, finding_count, verdict, dry_run)

    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(content)
    else:
        print(content, end="")

    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
