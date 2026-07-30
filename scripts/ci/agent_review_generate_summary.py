#!/usr/bin/env python3
"""Generate step summary for an agent review.

Replaces the 'shell: python3 {0}' inline block in
.github/actions/agent-review/action.yml (ADR-006).

Retains the sys.path.insert(0, GITHUB_WORKSPACE) pattern so
scripts.ai_review_common.issue_triage resolves correctly.

ENV:
  AGENT                - agent name
  EMOJI                - display emoji
  VERDICT              - review verdict
  FINDINGS             - review findings text
  RUN_ID               - workflow run ID
  SERVER_URL           - GitHub server URL
  REPOSITORY           - owner/repo
  PR_NUMBER            - pull request number
  CACHE_HIT            - "true" if cached results were used
  GITHUB_WORKSPACE     - workspace root (for sys.path)
  GITHUB_STEP_SUMMARY  - path to the step summary file

EXIT CODES (ADR-035):
  0 - summary written
  1 - unexpected error during generation
"""

from __future__ import annotations

import os
import sys


def run(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Generate and write the step summary."""
    github_workspace = os.environ.get("GITHUB_WORKSPACE", "")
    if github_workspace:
        sys.path.insert(0, github_workspace)

    try:
        from scripts.ai_review_common.issue_triage import (  # noqa: PLC0415
            get_verdict_alert_type,
            get_verdict_emoji,
        )

        verdict = os.environ.get("VERDICT", "").strip() or "NEEDS_REVIEW"
        if not os.environ.get("VERDICT", "").strip():
            print(
                "::warning::VERDICT environment variable is missing or empty,"
                " defaulting to NEEDS_REVIEW"
            )

        agent = os.environ.get("AGENT", "")
        emoji = os.environ.get("EMOJI", "")
        findings = os.environ.get("FINDINGS", "")
        run_id = os.environ.get("RUN_ID", "")
        server_url = os.environ.get("SERVER_URL", "")
        repository = os.environ.get("REPOSITORY", "")
        cache_hit = os.environ.get("CACHE_HIT", "") == "true"

        alert_type = get_verdict_alert_type(verdict)
        verdict_emoji = get_verdict_emoji(verdict)
        agent_display = agent.title() if agent else "Unknown"
        cache_label = " (cached)" if cache_hit else ""

        lines = [
            f"## {emoji} {agent_display} Review{cache_label}",
            "",
            f"> [!{alert_type}]",
            f"> {verdict_emoji} **Verdict: {verdict}**{cache_label}",
            "",
            "<details>",
            "<summary>Review Findings</summary>",
            "",
            findings,
            "",
            "</details>",
            "",
            "---",
            "",
            f"<sub>💡 See the [workflow run]({server_url}/{repository}/actions/runs/{run_id})"
            " for full context across all agents, or check the PR for the"
            " consolidated quality gate comment.</sub>",
        ]
        summary = "\n".join(lines) + "\n"

        summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as fh:
                fh.write(summary)
        else:
            print(summary, end="")

        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"::error::Failed to generate step summary: {exc}")
        print(f"::error::Verdict: {os.environ.get('VERDICT', 'N/A')}")
        print(f"::error::Agent: {os.environ.get('AGENT', 'N/A')}")
        return 1


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
