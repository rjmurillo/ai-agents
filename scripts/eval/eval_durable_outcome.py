#!/usr/bin/env python3
"""Read durable-outcome JSONL records and print a report or matched comparison.

Thin CLI over `scripts/eval/_durable_outcome.py` (REQ-042, DESIGN-040). Reads
one or two local JSONL files, one `OutcomeRecord` per line, and prints a
JSON `ConfigurationReport` (`--records` alone) or a JSON `Comparison`
(`--records` plus `--baseline`) to stdout. No network, no model calls; paths
come from argv and are opened read-only (REQ-042 "Security").

    eval_durable_outcome.py --records RUN.jsonl [--baseline BASE.jsonl]

Exit codes (DESIGN-040 "CLI"): 0 the printed report's status is `VERIFIED`, or,
with `--baseline`, the comparison result is `BETTER` or `MIXED`. 1 the
report's status is `UNVERIFIED`, or the comparison result is `WORSE` or
`UNVERIFIED`. 2 a JSONL parse error, a record-parse refusal, or a
comparison refusal (mismatched config field or task set); the error names
the offending line number or field on stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from _durable_outcome import build_report, compare
from _outcome_record import DurableOutcomeError, OutcomeRecord, parse_record

EXIT_OK = 0
EXIT_UNVERIFIED_OR_WORSE = 1
EXIT_INPUT_ERROR = 2

_FAILING_COMPARISON_RESULTS = frozenset({"WORSE", "UNVERIFIED"})


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DurableOutcomeError(f"cannot read {path}: {exc}") from exc


def _parse_line(path: Path, line_number: int, line: str) -> OutcomeRecord:
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise DurableOutcomeError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
    try:
        return parse_record(data)
    except DurableOutcomeError as exc:
        raise DurableOutcomeError(f"{path}:{line_number}: {exc}") from exc


def read_records(path: Path) -> list[OutcomeRecord]:
    """Read one OutcomeRecord per non-blank line of a local JSONL file.

    Blank lines are skipped. A malformed line's error names the 1-based line
    number (REQ-042 failure mode table: "Malformed record").
    """
    records: list[OutcomeRecord] = []
    for line_number, line in enumerate(_read_text(path).splitlines(), start=1):
        if not line.strip():
            continue
        records.append(_parse_line(path, line_number, line))
    if not records:
        raise DurableOutcomeError(f"{path}: no records found")
    return records


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="Candidate JSONL records")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Baseline JSONL records for a matched comparison",
    )
    return parser


def _exit_code_for_report(report: dict[str, object]) -> int:
    return EXIT_OK if report["status"] == "VERIFIED" else EXIT_UNVERIFIED_OR_WORSE


def _exit_code_for_comparison(comparison: dict[str, object]) -> int:
    return (
        EXIT_UNVERIFIED_OR_WORSE
        if comparison["result"] in _FAILING_COMPARISON_RESULTS
        else EXIT_OK
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        candidate_records = read_records(args.records)
        if args.baseline is not None:
            baseline_records = read_records(args.baseline)
            comparison = compare(baseline_records, candidate_records)
            print(json.dumps(comparison, indent=2))
            return _exit_code_for_comparison(comparison)
        report = build_report(candidate_records)
        print(json.dumps(report, indent=2))
        return _exit_code_for_report(report)
    except DurableOutcomeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR


# pragma: no cover on the entry-point guard: it only runs when this file is
# the process entry point, which is a different interpreter than the one
# pytest-cov instruments. `test_script_run_as_main_exits_0_on_pass_report`
# drives it end to end through a real subprocess instead.
if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
