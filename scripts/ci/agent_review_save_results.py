#!/usr/bin/env python3
"""Save review results to the ai-review-results directory.

Replaces the PowerShell 'Save review results' block in
.github/actions/agent-review/action.yml (ADR-006).

ENV:
  AGENT                  - agent name (validated against allowlist)
  VERDICT                - review verdict
  FINDINGS               - review findings text
  INFRASTRUCTURE_FAILURE - whether review failed due to infra issues
  RETRY_COUNT            - number of retries attempted
  CACHE_HIT              - "true" if cached results were used

EXIT CODES (ADR-035):
  0 - results saved
  1 - AGENT not in allowlist
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ALLOWED_AGENTS = frozenset(
    {
        "security",
        "qa",
        "analyst",
        "architect",
        "devops",
        "roadmap",
        "reliability",
        "observability",
        "agent-safety",
        "decision-rigor",
    }
)


def run(argv: list[str] | None = None) -> int:  # noqa: ARG001
    """Validate agent and save review result files."""
    agent = os.environ.get("AGENT", "")
    if agent not in _ALLOWED_AGENTS:
        allowed = ", ".join(sorted(_ALLOWED_AGENTS))
        print(f"::error::Invalid agent name: {agent}. Must be one of: {allowed}")
        return 1

    verdict = os.environ.get("VERDICT", "").strip()
    findings = os.environ.get("FINDINGS", "")
    infra_failure = os.environ.get("INFRASTRUCTURE_FAILURE", "")
    retry_count = os.environ.get("RETRY_COUNT", "0")
    cache_hit = os.environ.get("CACHE_HIT", "")

    if not verdict:
        verdict = "NEEDS_REVIEW"
        print("::warning::Verdict was empty, defaulting to NEEDS_REVIEW")
        if not findings:
            infra_failure = "true"
            print(
                "::warning::Both verdict and findings are empty, marking as infrastructure failure"
            )
    os.environ["INFRASTRUCTURE_FAILURE"] = infra_failure

    if cache_hit == "true":
        print(f"Using cached review result for {agent}")

    base_path = Path("ai-review-results")
    base_path.mkdir(exist_ok=True)

    (base_path / f"{agent}-verdict.txt").write_text(verdict, encoding="utf-8")
    (base_path / f"{agent}-findings.txt").write_text(findings, encoding="utf-8")
    (base_path / f"{agent}-infrastructure-failure.txt").write_text(infra_failure, encoding="utf-8")
    (base_path / f"{agent}-retry-count.txt").write_text(retry_count, encoding="utf-8")

    findings_size = len(findings.encode())
    print(f"Saved {agent} results:")
    print(f"  Verdict: {verdict}")
    print(f"  Findings: {findings_size} bytes")
    print(f"  Infrastructure failure: {infra_failure}")
    print(f"  Retry count: {retry_count}")
    print(f"  Cache hit: {cache_hit}")
    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
