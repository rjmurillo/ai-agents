#!/usr/bin/env python3
"""Save review results to the ai-review-results directory.

Replaces the PowerShell 'Save review results' block in
.github/actions/agent-review/action.yml (ADR-006).

The artifact this writes is what ``AI Quality Gate Results`` downloads, so it
must be written even when the review never ran. Issue #4778: an infrastructure
skip that writes nothing makes ``validate_artifact_download.py`` exit 1 on a
missing verdict file, and the gate fails before it can say why. The verdict
fallback ladder lives in ``scripts/ci/agent_review_outcome.py``.

ENV:
  AGENT                  - agent name (validated against allowlist)
  VERDICT                - review verdict
  FINDINGS               - review findings text
  INFRASTRUCTURE_FAILURE - whether review failed due to infra issues
  INFRA_READY            - "true" when the preflight cleared the model call
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

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The composite action executes this file directly, so bootstrap must precede
# the package import when the repository is not installed.
from scripts.ci.agent_review_outcome import resolve_outcome  # noqa: E402

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


def run(_argv: list[str] | None = None) -> int:
    """Validate agent and save review result files."""
    agent = os.environ.get("AGENT", "")
    if agent not in _ALLOWED_AGENTS:
        allowed = ", ".join(sorted(_ALLOWED_AGENTS))
        print(f"::error::Invalid agent name: {agent}. Must be one of: {allowed}")
        return 1

    retry_count = os.environ.get("RETRY_COUNT", "0")
    cache_hit = os.environ.get("CACHE_HIT", "")

    outcome = resolve_outcome(
        verdict=os.environ.get("VERDICT", ""),
        findings=os.environ.get("FINDINGS", ""),
        infrastructure_failure=os.environ.get("INFRASTRUCTURE_FAILURE", ""),
        infra_ready_value=os.environ.get("INFRA_READY"),
    )
    for annotation in outcome.annotations:
        print(annotation)
    verdict = outcome.verdict
    findings = outcome.findings
    infra_failure = outcome.infrastructure_failure
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
