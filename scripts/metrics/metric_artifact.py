#!/usr/bin/env python3
"""Validate a backlog or RCA metric artifact before a report may print it (#5639).

The contract is one JSON object per metric. A producer fills it, this module
resolves the effective status, and ``scripts/metrics/metric_artifact_io.py``
decides whether the artifact may replace the last valid one.

Fields (all required unless marked)::

    schema_version  1
    metric, branch, cohort   non-empty strings (cohort defines the numerator/denominator)
    kind            stock_snapshot | event_flow | same_cohort_rate | reconstructed_estimate
    unit            issues | prs | reviews | trailers | receipts
    repository      owner/name
    source_revision 40-hex SHA or null; required when code_dependent is true
    code_dependent  true when interpreting the metric depends on source state
    retrieved_at    UTC ISO-8601 (zero offset)
    query           {"parameters": {...}} as sent to the API
    pagination      {complete, pages_fetched, failed_page, failed_record, failure}
    window          {start, end, timezone: "UTC"}; start may be null for a stock snapshot
    numerator, denominator   non-negative int or null
    counts          {raw, derived, null, duplicates, excluded}
    status          PASS | WARN | BLOCKED | INVALID
    limitations, excluded_data   lists of strings

Rules the validator enforces: ``raw == derived + null + duplicates + excluded``;
``numerator == derived`` for a stock or flow, ``denominator == derived`` and
``numerator <= denominator`` for a same-cohort rate; incomplete pagination is
BLOCKED and must name the failed page or record; a stale, future, or
unparseable timestamp is BLOCKED or INVALID; BLOCKED and INVALID artifacts
carry null numbers. The effective status is the worst of the declared status
and every finding, so a producer cannot understate a problem.

Exit codes (ADR-035): 0 PASS or WARN, 1 BLOCKED or INVALID, 2 unreadable input.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

# The repository root must be importable when this runs as a plain script.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.metrics.metric_artifact_checks import (  # noqa: E402  (path set above)
    STATUSES,
    Finding,
    check_counts,
    check_declaration,
    check_envelope,
    check_numbers,
    check_pagination,
    check_revision,
    check_time,
    severity,
)

DEFAULT_MAX_AGE = timedelta(hours=24)
EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_CONFIG = 2


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """The effective status of an artifact and every finding behind it."""

    status: str
    findings: tuple[Finding, ...]

    @property
    def reportable(self) -> bool:
        """True when a report may print the number (PASS, or WARN as provisional)."""
        return self.status in ("PASS", "WARN")


def validate_artifact(
    payload: object, *, now: datetime, max_age: timedelta = DEFAULT_MAX_AGE
) -> ValidationResult:
    """Return the effective status for ``payload`` as of ``now``. Never raises on bad input."""
    if not isinstance(payload, Mapping):
        finding = Finding("INVALID", "artifact", "must be a JSON object")
        return ValidationResult("INVALID", (finding,))
    findings = [
        *check_envelope(payload),
        *check_revision(payload),
        *check_time(payload, now=now, max_age=max_age),
        *check_pagination(payload),
        *check_counts(payload),
        *check_numbers(payload),
        *check_declaration(payload),
    ]
    declared = payload.get("status")
    worst = max([severity("PASS"), *(severity(f.status) for f in findings)])
    if declared in STATUSES:
        worst = max(worst, severity(declared))
    return ValidationResult(STATUSES[worst], tuple(findings))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a metric artifact JSON file.")
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--max-age-hours", type=float, default=DEFAULT_MAX_AGE.total_seconds() / 3600
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Prints one line per finding, then the effective status."""
    args = _parse_args(argv)
    try:
        payload = json.loads(args.path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot read {args.path}: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    result = validate_artifact(
        payload,
        now=datetime.now(timezone.utc),
        max_age=timedelta(hours=args.max_age_hours),
    )
    for finding in result.findings:
        print(f"{finding.status} {finding.field}: {finding.message}")
    print(result.status)
    return EXIT_OK if result.reportable else EXIT_REJECTED


if __name__ == "__main__":
    sys.exit(main())
