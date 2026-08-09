#!/usr/bin/env python3
"""Check review verdict and fail the step if blocking.

Replaces the PowerShell 'Check verdict and fail if needed' block in
.github/actions/agent-review/action.yml (ADR-006).

Blocking verdicts: CRITICAL_FAIL, REJECTED, FAIL, NEEDS_REVIEW.
Infrastructure failures (INFRASTRUCTURE_FAILURE=true) defer the merge decision
to the aggregate gate instead of failing the per-agent step.

ENV:
  AGENT                  - agent name
  EMOJI                  - display emoji
  VERDICT                - review verdict
  FINDINGS               - review findings text
  INFRASTRUCTURE_FAILURE - "true" if review failed due to infra issues

EXIT CODES (ADR-035):
  0 - verdict is not blocking, or an infra failure is deferred to the aggregate
  1 - verdict is blocking and not an infra failure
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The composite action executes this file directly, so bootstrap must precede
# the package import when the repository is not installed.
from scripts.ai_review_common import FAIL_VERDICTS, merge_verdicts  # noqa: E402

_BLOCKING_VERDICTS = frozenset(FAIL_VERDICTS | {"UNKNOWN", "DID_NOT_RUN"})
_MAX_ANNOTATION_LENGTH = 180


def run(_argv: list[str] | None = None) -> int:
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

    # The aggregate owns the final gate decision for infrastructure failures.
    if infra_failure == "true":
        print(
            f"::warning::[{agent}] Infrastructure failure (verdict: {verdict}). "
            "Deferring PR status to AI Quality Gate Results."
        )
        print()
        print(f"⚠️ {emoji} {agent} review did not run due to infrastructure failure")
        print()
        print("AI Quality Gate Results decides whether this blocks the PR.")
        return 0

    normalized_verdict = merge_verdicts([verdict])
    if normalized_verdict not in {"CRITICAL_FAIL", "UNKNOWN"}:
        print(f"✅ {emoji} {agent} review passed with verdict: {verdict}")
        return 0

    # Blocking verdict - compute annotation
    if not findings:
        summary = "Review failed but no details were provided by the AI model"
        print(f"::warning::[{agent}] Verdict is {verdict} but findings are empty")
    else:
        summary = findings.replace("\n", " ")
        if len(summary) > _MAX_ANNOTATION_LENGTH:
            summary = summary[: _MAX_ANNOTATION_LENGTH - 3] + "..."

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
