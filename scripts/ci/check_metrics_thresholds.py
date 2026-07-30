#!/usr/bin/env python3
"""Check agent metric thresholds and write outputs for the workflow.

Runs collect_metrics.py --output json, parses the result, compares coverage
and infrastructure-review rate against targets, and writes coverage,
infra_rate, and alert to GITHUB_OUTPUT.
Replaces the "Check thresholds" step in agent-metrics.yml (issue #3531).

EXIT CODES (ADR-035):
  0  - Thresholds checked and outputs written
  1  - collect_metrics.py failed or output unparseable
  2  - Usage error
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

_COLLECT_SCRIPT = ".claude/skills/metrics/collect_metrics.py"
_COVERAGE_TARGET = 50.0
_INFRA_RATE_TARGET = 100.0


def collect_metrics_json(since: int = 7) -> dict[str, Any]:
    """Run collect_metrics.py --output json and return the parsed dict."""
    result = subprocess.run(
        [sys.executable, _COLLECT_SCRIPT, "--since", str(since), "--output", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"collect_metrics.py failed: {result.stderr.strip()}")
    return dict(json.loads(result.stdout))


def check_thresholds(metrics: dict[str, Any]) -> tuple[float, float, int, bool]:
    """Return (coverage, infra_rate, infra_commits, alert).

    Compares values against defined targets and prints warning annotations.
    """
    coverage: float = float(metrics["metric_2_coverage"]["coverage_rate"])
    infra_rate: float = float(metrics["metric_4_infrastructure_review"]["review_rate"])
    infra_commits: int = int(metrics["metric_4_infrastructure_review"]["infrastructure_commits"])

    alert = False

    if coverage < _COVERAGE_TARGET:
        print(f"::warning::Agent coverage ({coverage}%) is below target ({_COVERAGE_TARGET}%)")
        alert = True

    if infra_commits != 0 and infra_rate < _INFRA_RATE_TARGET:
        print(
            f"::warning::Infrastructure review rate ({infra_rate}%) "
            f"is below target ({_INFRA_RATE_TARGET}%)"
        )
        alert = True

    return coverage, infra_rate, infra_commits, alert


def write_github_output(
    coverage: float,
    infra_rate: float,
    alert: bool,
    output_file: str,
) -> None:
    """Append coverage, infra_rate, alert to GITHUB_OUTPUT."""
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(f"coverage={coverage}\n")
        f.write(f"infra_rate={infra_rate}\n")
        f.write(f"alert={str(alert).lower()}\n")


def main(argv: list[str] | None = None) -> int:
    try:
        metrics = collect_metrics_json()
    except (RuntimeError, json.JSONDecodeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR

    coverage, infra_rate, _infra_commits, alert = check_thresholds(metrics)

    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        write_github_output(coverage, infra_rate, alert, output_file)

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
