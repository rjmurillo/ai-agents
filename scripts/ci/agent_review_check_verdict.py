#!/usr/bin/env python3
"""Check review verdict and fail the step if blocking.

Replaces the PowerShell 'Check verdict and fail if needed' block in
.github/actions/agent-review/action.yml (ADR-006).

Blocking verdicts: CRITICAL_FAIL, REJECTED, FAIL, NEEDS_REVIEW.
Infrastructure failures (INFRASTRUCTURE_FAILURE=true) downgrade to
a warning instead of failing the step.

ENV:
  AGENT                  - agent name
  EMOJI                  - display emoji
  VERDICT                - review verdict
  FINDINGS               - review findings text
  INFRASTRUCTURE_FAILURE - "true" if review failed due to infra issues

EXIT CODES (ADR-035):
  0 - verdict is not blocking, or blocking due to infra failure (downgraded)
  1 - verdict is blocking and not an infra failure
"""

from __future__ import annotations

import os
import sys

_BLOCKING_VERDICTS = frozenset({"CRITICAL_FAIL", "REJECTED", "FAIL", "NEEDS_REVIEW"})
_MAX_ANNOTATION_LENGTH = 180


def run(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Check verdict and exit with appropriate code."""
    agent = os.environ.get("AGENT", "")
    emoji = os.environ.get("EMOJI", "")
    verdict = os.environ.get("VERDICT", "").strip()
    findings = os.environ.get("FINDINGS", "")
    infra_failure = os.environ.get("INFRASTRUCTURE_FAILURE", "")

    if not verdict:
        verdict = "NEEDS_REVIEW"
        print("::warning::Verdict was empty, defaulting to NEEDS_REVIEW")
        if not findings:
            infra_failure = "true"
            print(
                "::warning::Both verdict and findings are empty, treating as infrastructure failure"
            )

    if verdict not in _BLOCKING_VERDICTS:
        print(f"✅ {emoji} {agent} review passed with verdict: {verdict}")
        return 0

    # Infrastructure failures are non-blocking (aggregate handles downgrade)
    if infra_failure == "true":
        print(f"::warning::[{agent}] Infrastructure failure (verdict: {verdict}). Not blocking PR.")
        print()
        print(f"⚠️ {emoji} {agent} review had infrastructure failure (Copilot CLI unavailable)")
        print()
        print("Verdict downgraded by aggregate step. See workflow summary for details.")
        return 0

    # Blocking verdict - compute annotation
    if not findings:
        summary = "Review failed but no details were provided by the AI model"
        print(f"::warning::[{agent}] Verdict is {verdict} but findings are empty")
    else:
        summary = findings.replace("\n", " ")
        if len(summary) > _MAX_ANNOTATION_LENGTH:
            summary = summary[: _MAX_ANNOTATION_LENGTH - 3] + "..."

    # Check inner infra failure (preserved for behavioral parity even though
    # the outer early-exit above makes it logically unreachable in practice)
    if os.environ.get("INFRASTRUCTURE_FAILURE", "") == "true":
        print(
            f"::warning::[{agent}] {verdict}: {summary}"
            " (infrastructure failure, downgrading to warning)"
        )
        print()
        print(f"⚠️ {emoji} {agent} review had infrastructure failure (verdict: {verdict})")
        print()
        print("Infrastructure failures are non-blocking. See aggregate results for final verdict.")
        return 0

    print(f"::error::[{agent}] {verdict}: {summary}")
    print()
    print(f"❌ {emoji} {agent} review failed with verdict: {verdict}")
    print()
    print("See the step summary above for full findings.")
    return 1


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
