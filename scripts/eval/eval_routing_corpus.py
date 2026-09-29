#!/usr/bin/env python3
"""Validate the routing benchmark corpus and prove its graders discriminate.

Thin CLI over `_routing_scenario.py` and `_routing_grader.py` (issue #5425).
Loads every scenario under `--corpus`, then runs each scenario's controls:
known-good PASS, known-bad FAIL, untouched baseline FAIL, reset
reproducibility, plus the category 4 and category 5 checks. No network and no
model calls. The validation commands run `python` scripts that ship inside the
corpus fixtures, in scratch directories.

    eval_routing_corpus.py [--corpus DIR]

Exit codes: 0 every scenario loaded and every control held. 1 a control
failed. 2 the corpus is invalid (parse, schema, missing category, missing
fixture, model name, answer-key leak). The JSON report on stdout carries the
number of scenarios examined next to the number that failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from _routing_grader import ControlReport, verify_controls
from _routing_scenario import RoutingCorpusError, load_corpus

EXIT_OK = 0
EXIT_CONTROL_FAILED = 1
EXIT_CORPUS_INVALID = 2

DEFAULT_CORPUS = Path(__file__).resolve().parents[2] / "evals" / "routing-benchmark" / "scenarios"


def _report_dict(report: ControlReport, category: str, difficulty: str) -> dict[str, object]:
    return {
        "id": report.scenario_id,
        "category": category,
        "difficulty": difficulty,
        "ok": report.ok,
        "checks": [
            {"name": check.name, "ok": check.ok, "detail": check.detail} for check in report.checks
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args(argv)
    try:
        scenarios = load_corpus(args.corpus)
    except RoutingCorpusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CORPUS_INVALID
    rows = [
        _report_dict(verify_controls(item), item.category.value, item.difficulty.value)
        for item in scenarios
    ]
    failed = sum(1 for row in rows if not row["ok"])
    print(json.dumps({"examined": len(rows), "failed": failed, "scenarios": rows}, indent=2))
    return EXIT_CONTROL_FAILED if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
