#!/usr/bin/env python3
"""Measure context-retrieval auto-invocation metrics from session logs.

Parses session logs in .agents/sessions/ to extract metrics about
context-retrieval agent invocations during orchestration.

EXIT CODES:
  0  - Success: Metrics collected and reported
  1  - Error: No session logs found or parsing failed
  2  - Error: Unexpected error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class InvocationRecord:
    """A single context-retrieval invocation or skip decision."""

    session_id: str
    complexity: str
    domains: list[str]
    invoked: bool
    reason: str


@dataclass
class Metrics:
    """Aggregated context-retrieval metrics."""

    total_eligible: int = 0
    total_invoked: int = 0
    total_skipped: int = 0
    invocations: list[InvocationRecord] = field(default_factory=list)

    @property
    def invocation_rate(self) -> float:
        """Percentage of eligible tasks where context-retrieval was invoked."""
        if self.total_eligible == 0:
            return 0.0
        return (self.total_invoked / self.total_eligible) * 100

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        return {
            "total_eligible": self.total_eligible,
            "total_invoked": self.total_invoked,
            "total_skipped": self.total_skipped,
            "invocation_rate_percent": round(self.invocation_rate, 1),
            "targets": {
                "auto_invocation_rate": {
                    "target": ">=90%",
                    "actual": f"{self.invocation_rate:.1f}%",
                },
                "token_overhead": {
                    "target": "<5000",
                    "actual": "N/A (requires runtime measurement)",
                },
                "context_reuse": {
                    "target": ">60%",
                    "actual": "N/A (requires downstream tracking)",
                },
                "false_positive_rate": {
                    "target": "<20%",
                    "actual": "N/A (requires relevance scoring)",
                },
            },
            "invocations": [
                {
                    "session": r.session_id,
                    "complexity": r.complexity,
                    "domains": r.domains,
                    "invoked": r.invoked,
                    "reason": r.reason,
                }
                for r in self.invocations
            ],
        }


def find_session_logs(sessions_dir: Path) -> list[Path]:
    """Find all JSON session logs in the sessions directory."""
    if not sessions_dir.is_dir():
        return []
    return sorted(sessions_dir.glob("*.json"), key=lambda p: p.name, reverse=True)


def extract_context_retrieval_data(session_path: Path) -> InvocationRecord | None:
    """Extract context-retrieval invocation data from a session log.

    Looks for the classification summary in session logs that includes
    the Context Retrieval tracking fields added by Step 3.5.
    """
    try:
        content = session_path.read_text(encoding="utf-8")
        session = json.loads(content)
    except (json.JSONDecodeError, OSError):
        return None

    session_id = session_path.stem

    # Check for context-retrieval tracking in outcomes or decisions
    outcomes = session.get("outcomes", [])
    decisions = session.get("decisions", [])
    all_text = " ".join(str(o) for o in outcomes) + " ".join(str(d) for d in decisions)

    # Look for classification data in the session
    complexity = "unknown"
    domains: list[str] = []
    invoked = False
    reason = "no classification data found"

    # Check if orchestrator classification is recorded
    classification = session.get("classification", {})
    if classification:
        complexity = classification.get("complexity", "unknown")
        domains = classification.get("secondary_domains", [])
        cr_status = classification.get("context_retrieval", "")
        invoked = cr_status.upper() == "INVOKED"
        reason = classification.get("context_retrieval_reason", "")

    # Fallback: search text fields for context-retrieval mentions
    if complexity == "unknown" and "context-retrieval" in all_text.lower():
        invoked = "invoked" in all_text.lower() and "context-retrieval" in all_text.lower()
        reason = "inferred from session text"

    # Only return if we found orchestration evidence
    if complexity != "unknown" or "orchestrat" in all_text.lower():
        return InvocationRecord(
            session_id=session_id,
            complexity=complexity,
            domains=domains,
            invoked=invoked,
            reason=reason,
        )

    return None


def collect_metrics(sessions_dir: Path, limit: int = 50) -> Metrics:
    """Collect context-retrieval metrics from session logs."""
    metrics = Metrics()
    logs = find_session_logs(sessions_dir)

    for log_path in logs[:limit]:
        record = extract_context_retrieval_data(log_path)
        if record is None:
            continue

        metrics.total_eligible += 1
        if record.invoked:
            metrics.total_invoked += 1
        else:
            metrics.total_skipped += 1
        metrics.invocations.append(record)

    return metrics


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Measure context-retrieval auto-invocation metrics"
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=None,
        help="Path to sessions directory (default: .agents/sessions/)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of session logs to analyze (default: 50)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    args = parser.parse_args()

    # Determine sessions directory
    project_root = Path(__file__).resolve().parent.parent
    sessions_dir = args.sessions_dir or (project_root / ".agents" / "sessions")

    if not sessions_dir.is_dir():
        print(f"[ERROR] Sessions directory not found: {sessions_dir}", file=sys.stderr)
        return 1

    metrics = collect_metrics(sessions_dir, limit=args.limit)

    if args.format == "json":
        print(json.dumps(metrics.to_dict(), indent=2))
    else:
        print("=== Context-Retrieval Auto-Invocation Metrics ===")
        print(f"Sessions analyzed: {len(metrics.invocations)}")
        print(f"Eligible orchestrations: {metrics.total_eligible}")
        print(f"Context-retrieval invoked: {metrics.total_invoked}")
        print(f"Context-retrieval skipped: {metrics.total_skipped}")
        print(f"Invocation rate: {metrics.invocation_rate:.1f}%")
        print()
        print("--- Targets ---")
        print(f"  Auto-invocation rate: {metrics.invocation_rate:.1f}% (target: >=90%)")
        print("  Token overhead: N/A (requires runtime measurement)")
        print("  Context reuse: N/A (requires downstream tracking)")
        print("  False positive rate: N/A (requires relevance scoring)")

        if metrics.invocations:
            print()
            print("--- Recent Invocations ---")
            for record in metrics.invocations[:10]:
                status = "INVOKED" if record.invoked else "SKIPPED"
                print(
                    f"  {record.session_id}: {status}"
                    f" (complexity={record.complexity},"
                    f" reason={record.reason})"
                )

    return 0


if __name__ == "__main__":
    sys.exit(main())
