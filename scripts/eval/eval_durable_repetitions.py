#!/usr/bin/env python3
"""Print per-repeat counts and variance for durable-outcome JSONL (issue #5768).

    eval_durable_repetitions.py --records RUN.jsonl [--records RUN2.jsonl ...]

Several `--records` files are concatenated, so chunked runs (one file per
repeat, or a re-run of one failed cell) read as one configuration. Exit codes:
0 report written. 2 a file is missing, malformed, or holds mixed configurations
a repeated `task_id`/`repeat` pair, or repeats that cover different tasks.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from _durable_outcome import build_report
from _durable_repetitions import repetition_summary
from _outcome_record import DurableOutcomeError, OutcomeRecord, parse_record

EXIT_OK = 0
EXIT_INPUT = 2


def _read(path: Path) -> list[OutcomeRecord]:
    rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [parse_record(json.loads(line)) for line in rows]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--records", type=Path, action="append", required=True)
    args = parser.parse_args(argv)
    try:
        records = [record for path in args.records for record in _read(path)]
        build_report(records)  # refuses mixed configurations and duplicate task/repeat pairs
        summary = repetition_summary(records)
    except (OSError, UnicodeError, ValueError, DurableOutcomeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INPUT
    print(json.dumps(summary, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
