#!/usr/bin/env python3
"""Collect repository AI metrics for the weekly analysis workflow.

Extracted from ``.github/workflows/ai-metrics-analysis.yml`` under ADR-006
(no logic in workflow YAML). Issue #3539.

The shell this replaces computed a date window, called ``gh metrics`` twice,
and folded a failure of either call into a warning plus placeholder text. That
fail-soft behaviour is deliberate: a metrics outage must not fail the weekly
run, so it is preserved exactly. Both calls are made with an argument vector,
never a shell string, so a repository name cannot be word-split (CWE-78).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

_CSV_FALLBACK = "No CSV data available"
_TABLE_FALLBACK = "No table data available"
# A GITHUB_OUTPUT heredoc delimiter must not appear in the value it wraps.
_DELIMITER = "EOF_METRICS"


def _run_metrics(repository: str, start: str, end: str, *, csv: bool) -> str | None:
    """Return ``gh metrics`` output, or None when the call fails."""
    argv = ["gh", "metrics", "-R", repository, "-s", start, "-e", end]
    if csv:
        argv.append("--csv")
    sys.stdout.flush()
    completed = subprocess.run(
        argv,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        return None
    return completed.stdout


def _write_outputs(table: str, start: str, end: str, output_path: str | None) -> None:
    """Append the collected values to the GitHub Actions output file."""
    if _DELIMITER in table:
        # A value containing its own delimiter would let the table body inject
        # arbitrary step outputs.
        table = table.replace(_DELIMITER, _DELIMITER + "_ESCAPED")
    body = (
        f"metrics_table<<{_DELIMITER}\n{table}\n{_DELIMITER}\n"
        f"start_date={start}\nend_date={end}\n"
    )
    if not output_path:
        print(body, end="")
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        handle.write(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="owner/name to query.")
    parser.add_argument("--weeks", default="4", help="Window size in weeks.")
    parser.add_argument(
        "--csv-out",
        required=True,
        help="Where to write the CSV export.",
    )
    args = parser.parse_args(argv)

    try:
        weeks = int(args.weeks)
    except ValueError:
        print(f"::error::--weeks must be an integer, got {args.weeks!r}")
        return 1
    if weeks < 1:
        print(f"::error::--weeks must be at least 1, got {weeks}")
        return 1

    end_at = datetime.now(UTC).date()
    start_at = end_at - timedelta(weeks=weeks)
    end, start = end_at.isoformat(), start_at.isoformat()
    print(f"Collecting metrics from {start} to {end}")

    csv = _run_metrics(args.repository, start, end, csv=True)
    if csv is None:
        print("::warning::gh metrics CSV export failed")
        csv = _CSV_FALLBACK
    Path(args.csv_out).write_text(csv, encoding="utf-8")

    table = _run_metrics(args.repository, start, end, csv=False)
    if table is None:
        print("::warning::gh metrics table export failed")
        table = _TABLE_FALLBACK

    _write_outputs(table.rstrip("\n"), start, end, os.environ.get("GITHUB_OUTPUT"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
